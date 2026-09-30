"""Deterministic graders: exact, contains, regex, json_schema, numeric, python."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import math
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import jsonschema
import yaml

from evalkit.config import (
    ContainsGrader,
    ExactGrader,
    JsonSchemaGrader,
    NumericGrader,
    PythonGrader,
    RegexGrader,
)
from evalkit.graders.base import Grade, GradeContext, GraderError, as_text, extract_json
from evalkit.templating import render, render_value


def _resolve_value(value: Any, ctx: GradeContext) -> Any:
    if value is None:
        return ctx.task.expected
    return render_value(value, ctx.template_vars)


def _short(text: str, limit: int = 80) -> str:
    text = text.replace("\n", "\\n")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def grade_exact(config: ExactGrader, ctx: GradeContext) -> Grade:
    expected = as_text(_resolve_value(config.value, ctx))
    output = ctx.output
    if config.strip:
        expected, output = expected.strip(), output.strip()
    if config.ignore_case:
        expected, output = expected.casefold(), output.casefold()
    passed = output == expected
    reason = "matches" if passed else f"expected {_short(expected)!r}, got {_short(output)!r}"
    return Grade("exact", passed, float(passed), reason)


def grade_contains(config: ContainsGrader, ctx: GradeContext) -> Grade:
    raw = _resolve_value(config.value, ctx)
    needles = [as_text(item) for item in raw] if isinstance(raw, list) else [as_text(raw)]
    haystack = ctx.output.casefold() if config.ignore_case else ctx.output
    found = [n for n in needles if (n.casefold() if config.ignore_case else n) in haystack]
    missing = [n for n in needles if n not in found]
    if config.mode == "all":
        passed = not missing
        score = len(found) / len(needles) if needles else 1.0
        reason = "contains all" if passed else f"missing {', '.join(repr(m) for m in missing)}"
    else:
        passed = bool(found)
        score = float(passed)
        reason = f"contains {found[0]!r}" if found else "contains none of the values"
    return Grade("contains", passed, score, reason)


def grade_regex(config: RegexGrader, ctx: GradeContext) -> Grade:
    pattern = (
        render(config.pattern, ctx.template_vars) if "{{" in config.pattern else config.pattern
    )
    flags = re.IGNORECASE if config.ignore_case else 0
    try:
        compiled = re.compile(pattern, flags)
    except re.error as exc:
        raise GraderError(f"invalid regex {pattern!r}: {exc}") from exc
    match = (
        compiled.fullmatch(ctx.output.strip()) if config.fullmatch else compiled.search(ctx.output)
    )
    passed = match is not None
    reason = f"matched {_short(match.group(0))!r}" if match else f"no match for /{pattern}/"
    return Grade("regex", passed, float(passed), reason)


def _load_schema(config: JsonSchemaGrader, base_dir: Path) -> dict[str, Any]:
    if config.json_schema is not None:
        return config.json_schema
    assert config.schema_file is not None
    path = base_dir / config.schema_file
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GraderError(f"cannot read schema file {config.schema_file}: {exc.strerror}") from exc
    loaded = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise GraderError(f"schema file {config.schema_file} must contain an object")
    return loaded


def grade_json_schema(config: JsonSchemaGrader, ctx: GradeContext) -> Grade:
    schema = _load_schema(config, ctx.base_dir)
    try:
        data = extract_json(ctx.output) if config.extract else json.loads(ctx.output)
    except ValueError:
        return Grade("json_schema", False, 0.0, "output is not valid JSON")
    validator_cls = jsonschema.validators.validator_for(schema)
    try:
        validator_cls.check_schema(schema)
    except jsonschema.SchemaError as exc:
        raise GraderError(f"invalid JSON schema: {exc.message}") from exc
    errors = sorted(validator_cls(schema).iter_errors(data), key=lambda e: list(e.path))
    if not errors:
        return Grade("json_schema", True, 1.0, "valid")
    first = errors[0]
    location = "/".join(str(part) for part in first.path) or "(root)"
    more = f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""
    return Grade("json_schema", False, 0.0, f"{location}: {first.message}{more}")


_NUMBER = re.compile(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?|[-+]?\.\d+")


def parse_number(text: str, pick: str = "last") -> float | None:
    """Return the number in ``text``.

    The whole string wins if it is numeric. Otherwise the last number is used, since
    replies such as "17 * 23 = 391" end with the answer. Pass ``pick="first"`` to
    take the first number instead.
    """
    candidate = text.strip().rstrip(".")
    try:
        return float(candidate.replace(",", ""))
    except ValueError:
        pass
    matches = _NUMBER.findall(text)
    if not matches:
        return None
    chosen = matches[-1] if pick == "last" else matches[0]
    return float(chosen.replace(",", ""))


def grade_numeric(config: NumericGrader, ctx: GradeContext) -> Grade:
    raw = _resolve_value(config.value, ctx)
    try:
        expected = float(raw)
    except (TypeError, ValueError) as exc:
        raise GraderError(f"numeric grader: expected value {raw!r} is not a number") from exc
    actual = parse_number(ctx.output, config.pick)
    if actual is None:
        return Grade("numeric", False, 0.0, "no number in output")
    passed = math.isclose(actual, expected, rel_tol=config.rel_tol, abs_tol=config.abs_tol)
    reason = f"{actual:g} {'within' if passed else 'outside'} tolerance of {expected:g}"
    return Grade("numeric", passed, float(passed), reason)


_MODULES: dict[Path, ModuleType] = {}


def _load_function(spec: str, base_dir: Path) -> Any:
    target, _, name = spec.rpartition(":")
    if target.endswith(".py"):
        path = (base_dir / target).resolve()
        module = _MODULES.get(path)
        if module is None:
            if not path.is_file():
                raise GraderError(f"python grader: file not found: {target}")
            module_name = f"evalkit_user_{abs(hash(path))}"
            loader_spec = importlib.util.spec_from_file_location(module_name, path)
            if loader_spec is None or loader_spec.loader is None:  # pragma: no cover
                raise GraderError(f"python grader: cannot import {target}")
            module = importlib.util.module_from_spec(loader_spec)
            sys.modules[module_name] = module
            try:
                loader_spec.loader.exec_module(module)
            except Exception as exc:
                del sys.modules[module_name]
                raise GraderError(f"python grader: importing {target} failed: {exc!r}") from exc
            _MODULES[path] = module
    else:
        try:
            module = importlib.import_module(target)
        except ImportError as exc:
            raise GraderError(f"python grader: cannot import module {target!r}: {exc}") from exc
    function = getattr(module, name, None)
    if not callable(function):
        raise GraderError(f"python grader: {name!r} is not a function in {target}")
    return function


def _coerce_result(result: Any) -> tuple[bool, float, str]:
    if isinstance(result, bool):
        return result, float(result), ""
    if isinstance(result, int | float):
        score = max(0.0, min(1.0, float(result)))
        return score >= 0.5, score, ""
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], bool):
        return result[0], float(result[0]), str(result[1])
    if isinstance(result, dict) and "pass" in result:
        passed = bool(result["pass"])
        score = float(result.get("score", float(passed)))
        return passed, max(0.0, min(1.0, score)), str(result.get("reason", ""))
    raise GraderError(
        "python grader must return bool, a number in [0, 1], (bool, reason), "
        f"or {{'pass': ..., 'score': ..., 'reason': ...}}; got {type(result).__name__}"
    )


async def grade_python(config: PythonGrader, ctx: GradeContext) -> Grade:
    function = _load_function(config.function, ctx.base_dir)
    context = {**ctx.template_vars, "repeat": ctx.repeat, "seed": ctx.seed}
    try:
        result = function(ctx.output, context, **config.args)
        if inspect.isawaitable(result):
            result = await result
    except GraderError:
        raise
    except Exception as exc:
        raise GraderError(f"python grader {config.function} raised {exc!r}") from exc
    passed, score, reason = _coerce_result(result)
    return Grade(config.name or "python", passed, score, reason)
