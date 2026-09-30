"""Shared grader types."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evalkit.config import ProviderConfig, Task
from evalkit.providers.base import Request, Response

ModelCaller = Callable[[ProviderConfig | None, Request], Awaitable[Response]]


class GraderError(RuntimeError):
    """A grader could not run, for example a missing schema file or a crashing function."""


@dataclass
class Grade:
    grader: str
    passed: bool
    score: float
    reason: str = ""
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "grader": self.grader,
            "passed": self.passed,
            "score": round(self.score, 4),
            "reason": self.reason,
        }


@dataclass
class GradeContext:
    output: str
    task: Task
    prompt: str
    base_dir: Path
    call_model: ModelCaller | None = None
    seed: int = 0
    repeat: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def template_vars(self) -> dict[str, Any]:
        return task_context(self.task, prompt=self.prompt, output=self.output)


def task_context(task: Task, **extra: Any) -> dict[str, Any]:
    """Variables available to templates: input, expected, vars, id, metadata, and each var."""
    context: dict[str, Any] = dict(task.vars)
    context.update(
        {
            "id": task.id,
            "input": task.input,
            "expected": task.expected,
            "vars": task.vars,
            "metadata": task.metadata,
        }
    )
    if isinstance(task.input, dict):
        for key, value in task.input.items():
            context.setdefault(key, value)
    context.update(extra)
    return context


def as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply that may wrap it in prose or a code fence."""
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except ValueError:
        pass
    fence = "```"
    start = stripped.find(fence)
    while start != -1:
        body_start = stripped.find("\n", start)
        end = stripped.find(fence, body_start + 1) if body_start != -1 else -1
        if end == -1:
            break
        try:
            return json.loads(stripped[body_start + 1 : end])
        except ValueError:
            start = stripped.find(fence, end + len(fence))
    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char in "{[":
            try:
                value, _ = decoder.raw_decode(stripped, index)
            except ValueError:
                continue
            return value
    raise ValueError("no JSON value found in output")
