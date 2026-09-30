"""Suite file schema and loader.

A suite is a YAML (or JSON) document that describes the target under test, the
tasks to run, and the graders that decide whether each output passes.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_validator,
)


class ConfigError(ValueError):
    """Raised when a suite file cannot be loaded or fails validation."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --------------------------------------------------------------------------- providers


class Pricing(_Strict):
    """Prices in USD per million tokens. You supply them; evalkit ships no price table."""

    input_per_mtok: float = Field(0.0, ge=0)
    output_per_mtok: float = Field(0.0, ge=0)


class _ProviderBase(_Strict):
    timeout: float = Field(60.0, gt=0, description="Per-request timeout in seconds.")
    pricing: Pricing | None = None
    cache: bool | None = Field(
        None, description="Override the cache default for this provider (models: on, apps: off)."
    )


class MockRule(_Strict):
    match: str = Field(description="Regular expression searched against the rendered prompt.")
    output: str
    flaky: float | None = Field(None, ge=0, le=1, description="Overrides the provider's flaky.")

    @field_validator("match")
    @classmethod
    def _valid_regex(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid regex {value!r}: {exc}") from exc
        return value


class MockProviderConfig(_ProviderBase):
    provider: Literal["mock"]
    model: str = "mock"
    responses: list[MockRule] = Field(default_factory=list)
    default: str | None = Field(None, description="Output when no rule matches. Echoes if unset.")
    latency_ms: float = Field(0.0, ge=0)
    flaky: float = Field(
        0.0, ge=0, le=1, description="Probability, per seed and repeat, of returning flaky_output."
    )
    flaky_output: str = ""
    fail_times: int = Field(
        0, ge=0, description="Raise a retriable error this many times per request before answering."
    )


class OpenAIProviderConfig(_ProviderBase):
    provider: Literal["openai"]
    model: str
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str | None = "OPENAI_API_KEY"
    temperature: float | None = None
    max_tokens: int | None = Field(None, gt=0)
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict, description="Extra request body fields.")


class AnthropicProviderConfig(_ProviderBase):
    provider: Literal["anthropic"]
    model: str
    base_url: str = "https://api.anthropic.com"
    api_key_env: str | None = "ANTHROPIC_API_KEY"
    anthropic_version: str = "2023-06-01"
    temperature: float | None = None
    max_tokens: int = Field(1024, gt=0)
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)


class CommandProviderConfig(_ProviderBase):
    provider: Literal["command"]
    command: str | list[str] = Field(
        description="Program to run. The prompt goes to stdin unless an argument contains {{prompt}}."
    )
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    model: str = "command"


class HttpProviderConfig(_ProviderBase):
    provider: Literal["http"]
    url: str
    method: Literal["POST", "PUT", "GET"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = Field(
        default_factory=lambda: {"input": "{{prompt}}"},
        description="JSON body template. Strings may reference {{prompt}}, {{system}}, {{vars.*}}.",
    )
    output_path: str | None = Field(
        None, description="Dotted path into the JSON response, e.g. 'data.answer'."
    )
    model: str = "http"


ProviderConfig = Annotated[
    MockProviderConfig
    | OpenAIProviderConfig
    | AnthropicProviderConfig
    | CommandProviderConfig
    | HttpProviderConfig,
    Field(discriminator="provider"),
]

# ----------------------------------------------------------------------------- graders


class _GraderBase(_Strict):
    name: str | None = Field(None, description="Label shown in reports. Defaults to the type.")
    negate: bool = Field(False, description="Invert the verdict, e.g. 'must not contain'.")
    weight: float = Field(1.0, gt=0, description="Weight in the task score.")


class ExactGrader(_GraderBase):
    type: Literal["exact"]
    value: Any = Field(None, description="Expected output. Defaults to the task's expected.")
    ignore_case: bool = False
    strip: bool = True


class ContainsGrader(_GraderBase):
    type: Literal["contains"]
    value: Any = None
    mode: Literal["all", "any"] = "all"
    ignore_case: bool = False


class RegexGrader(_GraderBase):
    type: Literal["regex"]
    pattern: str
    ignore_case: bool = False
    fullmatch: bool = False

    @field_validator("pattern")
    @classmethod
    def _valid_regex(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid regex {value!r}: {exc}") from exc
        return value


class JsonSchemaGrader(_GraderBase):
    type: Literal["json_schema"]
    json_schema: dict[str, Any] | None = Field(None, alias="schema")
    schema_file: str | None = None
    extract: bool = Field(
        True, description="Pull JSON out of Markdown code fences or surrounding prose."
    )

    @model_validator(mode="after")
    def _one_schema(self) -> JsonSchemaGrader:
        if (self.json_schema is None) == (self.schema_file is None):
            raise ValueError("set exactly one of 'schema' or 'schema_file'")
        return self


class NumericGrader(_GraderBase):
    type: Literal["numeric"]
    value: Any = None
    abs_tol: float = Field(0.0, ge=0)
    rel_tol: float = Field(0.0, ge=0)
    pick: Literal["last", "first"] = Field(
        "last", description="Which number to use when the output contains several."
    )


class PythonGrader(_GraderBase):
    type: Literal["python"]
    function: str = Field(
        description="'path/to/file.py:func' (relative to the suite) or 'package.module:func'."
    )
    args: dict[str, Any] = Field(default_factory=dict, description="Keyword arguments to pass.")

    @field_validator("function")
    @classmethod
    def _has_colon(cls, value: str) -> str:
        if ":" not in value:
            raise ValueError("expected 'file.py:function' or 'module:function'")
        return value


class LlmJudgeGrader(_GraderBase):
    type: Literal["llm_judge"]
    rubric: str
    provider: ProviderConfig | None = Field(
        None, description="Judge model. Defaults to the suite-level 'judge'."
    )
    scale: int = Field(5, ge=2, le=100, description="Scores range from 1 to scale.")
    min_score: float | None = Field(None, description="Passing score. Defaults to scale - 1.")


GraderConfig = Annotated[
    ExactGrader
    | ContainsGrader
    | RegexGrader
    | JsonSchemaGrader
    | NumericGrader
    | PythonGrader
    | LlmJudgeGrader,
    Field(discriminator="type"),
]

_NEEDS_EXPECTED = (ExactGrader, ContainsGrader, NumericGrader)

# ------------------------------------------------------------------------ tasks, suite


class Task(_Strict):
    id: str | None = None
    input: Any = None
    vars: dict[str, Any] = Field(default_factory=dict)
    expected: Any = None
    graders: list[GraderConfig] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Settings(_Strict):
    concurrency: int = Field(4, ge=1, le=256)
    repeat: int = Field(1, ge=1, le=1000, description="Runs per task, for flakiness stats.")
    retries: int = Field(2, ge=0, le=20)
    retry_backoff: float = Field(0.5, ge=0, description="Base backoff in seconds (doubles).")
    seed: int = 0
    cache: bool = True
    cache_path: str = ".evalkit/cache.sqlite"
    fail_under: float = Field(
        1.0, ge=0, le=1, description="Minimum share of passing tasks for a zero exit code."
    )
    task_pass_rate: float = Field(
        1.0,
        ge=0,
        le=1,
        description="Share of a task's repeats that must pass for the task to pass.",
    )


class Suite(_Strict):
    version: Literal[1] = 1
    name: str
    description: str | None = None
    target: ProviderConfig
    judge: ProviderConfig | None = None
    system: str | None = None
    prompt: str | None = Field(
        None, description="Prompt template. Tasks fill it through input, vars, and expected."
    )
    graders: list[GraderConfig] = Field(
        default_factory=list, description="Graders applied to every task."
    )
    tasks: list[Task] = Field(min_length=1)
    settings: Settings = Field(default_factory=Settings)

    # Directory of the suite file, set by the loader. Relative paths resolve against it.
    _base_dir: Path = PrivateAttr(default_factory=Path.cwd)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @model_validator(mode="after")
    def _check_tasks(self) -> Suite:
        seen: set[str] = set()
        for index, task in enumerate(self.tasks):
            if task.id is None:
                task.id = f"task-{index + 1}"
            if task.id in seen:
                raise ValueError(f"duplicate task id '{task.id}'")
            seen.add(task.id)
            if self.prompt is None and not isinstance(task.input, str):
                raise ValueError(
                    f"task '{task.id}': 'input' must be a string when the suite has no 'prompt'"
                )
            graders = [*self.graders, *task.graders]
            if not graders:
                raise ValueError(f"task '{task.id}' has no graders")
            for grader in graders:
                if (
                    isinstance(grader, _NEEDS_EXPECTED)
                    and grader.value is None
                    and task.expected is None
                ):
                    raise ValueError(
                        f"task '{task.id}': grader '{grader.type}' needs a 'value' "
                        "or a task-level 'expected'"
                    )
                if (
                    isinstance(grader, LlmJudgeGrader)
                    and grader.provider is None
                    and self.judge is None
                ):
                    raise ValueError(
                        f"task '{task.id}': llm_judge needs a 'provider' or a suite-level 'judge'"
                    )
        return self

    def graders_for(self, task: Task) -> list[GraderConfig]:
        return [*self.graders, *task.graders]


# ------------------------------------------------------------------------------ loader

_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expand_env(value: Any) -> Any:
    """Expand ``${VAR}`` and ``${VAR:-default}`` in provider settings."""
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            name, default = match.group(1), match.group(2)
            if name in os.environ:
                return os.environ[name]
            if default is not None:
                return default
            raise ConfigError(f"environment variable '{name}' is not set")

        return _ENV.sub(replace, value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


def _read_structured(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc.strerror or exc}") from exc
    try:
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        if path.suffix == ".json":
            return json.loads(text)
        return yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot parse {path}: {exc}") from exc


def _format_validation_error(path: Path, exc: ValidationError) -> str:
    lines = [f"{path}: invalid suite"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "(root)"
        message = error["msg"].removeprefix("Value error, ")
        lines.append(f"  - {location}: {message}")
    return "\n".join(lines)


def parse_suite(data: Any, *, base_dir: Path, source: Path | None = None) -> Suite:
    """Validate an already-parsed suite document."""
    source = source or base_dir / "<suite>"
    if not isinstance(data, dict):
        raise ConfigError(f"{source}: expected a mapping at the top level")
    data = dict(data)
    tasks = data.get("tasks")
    if isinstance(tasks, str):
        tasks_path = (base_dir / tasks).resolve()
        loaded = _read_structured(tasks_path)
        if not isinstance(loaded, list):
            raise ConfigError(f"{tasks_path}: expected a list of tasks")
        data["tasks"] = loaded
    for key in ("target", "judge"):
        if isinstance(data.get(key), dict):
            data[key] = _expand_env(data[key])
    try:
        suite = Suite.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(source, exc)) from exc
    suite._base_dir = base_dir
    return suite


def load_suite(path: str | Path) -> Suite:
    """Load and validate a suite file."""
    suite_path = Path(path)
    return parse_suite(
        _read_structured(suite_path), base_dir=suite_path.parent.resolve(), source=suite_path
    )


def suite_json_schema() -> dict[str, Any]:
    """JSON Schema for suite files, for editor autocompletion."""
    schema = Suite.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "evalkit suite"
    return schema
