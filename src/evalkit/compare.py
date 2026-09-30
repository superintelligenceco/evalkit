"""Regression diff between two results files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class CompareError(ValueError):
    """Raised when a results file cannot be read."""


def load_results(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise CompareError(f"cannot read {path}: {exc.strerror or exc}") from exc
    except ValueError as exc:
        raise CompareError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or "tasks" not in data or "summary" not in data:
        raise CompareError(f"{path} is not an evalkit results file")
    return data


@dataclass
class TaskChange:
    id: str
    base_status: str | None
    head_status: str | None
    base_score: float | None
    head_score: float | None

    @property
    def delta(self) -> float:
        return (self.head_score or 0.0) - (self.base_score or 0.0)


@dataclass
class Comparison:
    base_pass_rate: float
    head_pass_rate: float
    base_score: float
    head_score: float
    threshold: float
    strict: bool
    regressed: list[TaskChange] = field(default_factory=list)
    fixed: list[TaskChange] = field(default_factory=list)
    score_changes: list[TaskChange] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def pass_rate_delta(self) -> float:
        return self.head_pass_rate - self.base_pass_rate

    @property
    def score_delta(self) -> float:
        return self.head_score - self.base_score

    @property
    def failures(self) -> list[str]:
        reasons = []
        if self.pass_rate_delta < -self.threshold - 1e-9:
            reasons.append(
                f"pass rate dropped {abs(self.pass_rate_delta) * 100:.1f} points "
                f"(threshold {self.threshold * 100:.1f})"
            )
        if self.score_delta < -self.threshold - 1e-9:
            reasons.append(
                f"score dropped {abs(self.score_delta):.3f} (threshold {self.threshold:.3f})"
            )
        if self.strict and self.regressed:
            reasons.append(f"{len(self.regressed)} task(s) regressed (strict mode)")
        return reasons

    @property
    def ok(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        def change(item: TaskChange) -> dict[str, Any]:
            return {
                "id": item.id,
                "base_status": item.base_status,
                "head_status": item.head_status,
                "base_score": item.base_score,
                "head_score": item.head_score,
            }

        return {
            "ok": self.ok,
            "failures": self.failures,
            "base": {"pass_rate": self.base_pass_rate, "score": self.base_score},
            "head": {"pass_rate": self.head_pass_rate, "score": self.head_score},
            "pass_rate_delta": round(self.pass_rate_delta, 4),
            "score_delta": round(self.score_delta, 4),
            "threshold": self.threshold,
            "strict": self.strict,
            "regressed": [change(item) for item in self.regressed],
            "fixed": [change(item) for item in self.fixed],
            "score_changes": [change(item) for item in self.score_changes],
            "added": self.added,
            "removed": self.removed,
        }


def compare(
    base: dict[str, Any], head: dict[str, Any], *, threshold: float = 0.0, strict: bool = False
) -> Comparison:
    """Compare two results dicts.

    Tasks match by id. A task regresses when it passed in ``base`` and does not pass
    in ``head``. The comparison fails when the pass rate or mean score drops by more
    than ``threshold`` (a fraction, so 0.05 is five points), or, in strict mode, when
    any task regresses.
    """
    base_tasks = {task["id"]: task for task in base["tasks"]}
    head_tasks = {task["id"]: task for task in head["tasks"]}
    result = Comparison(
        base_pass_rate=float(base["summary"]["pass_rate"]),
        head_pass_rate=float(head["summary"]["pass_rate"]),
        base_score=float(base["summary"]["score"]),
        head_score=float(head["summary"]["score"]),
        threshold=threshold,
        strict=strict,
    )
    for task_id, head_task in head_tasks.items():
        base_task = base_tasks.get(task_id)
        if base_task is None:
            result.added.append(task_id)
            continue
        item = TaskChange(
            id=task_id,
            base_status=base_task["status"],
            head_status=head_task["status"],
            base_score=base_task["score"],
            head_score=head_task["score"],
        )
        if base_task["passed"] and not head_task["passed"]:
            result.regressed.append(item)
        elif not base_task["passed"] and head_task["passed"]:
            result.fixed.append(item)
        elif abs(item.delta) >= 0.01:
            result.score_changes.append(item)
    result.removed = [task_id for task_id in base_tasks if task_id not in head_tasks]
    return result


def _signed(value: float, *, percent: bool = False) -> str:
    if percent:
        return f"{value * 100:+.1f} pts"
    return f"{value:+.3f}"


def render_comparison_text(result: Comparison) -> str:
    lines = [
        f"pass rate  {result.base_pass_rate * 100:.1f}% -> {result.head_pass_rate * 100:.1f}%  "
        f"({_signed(result.pass_rate_delta, percent=True)})",
        f"score      {result.base_score:.3f} -> {result.head_score:.3f}  ({_signed(result.score_delta)})",
    ]
    for title, items in (("regressed", result.regressed), ("fixed", result.fixed)):
        if items:
            lines.append(f"{title} ({len(items)}):")
            lines.extend(
                f"  {item.id}: {item.base_status} -> {item.head_status} "
                f"(score {item.base_score:.2f} -> {item.head_score:.2f})"
                for item in items
            )
    if result.score_changes:
        lines.append(f"score changed ({len(result.score_changes)}):")
        lines.extend(
            f"  {item.id}: {item.base_score:.2f} -> {item.head_score:.2f}"
            for item in result.score_changes
        )
    if result.added:
        lines.append(f"new tasks ({len(result.added)}): {', '.join(result.added)}")
    if result.removed:
        lines.append(f"removed tasks ({len(result.removed)}): {', '.join(result.removed)}")
    if result.ok:
        lines.append("OK: no regression beyond the threshold")
    else:
        lines.extend(f"REGRESSION: {reason}" for reason in result.failures)
    return "\n".join(lines)


def render_comparison_markdown(result: Comparison) -> str:
    verdict = "no regression" if result.ok else "regression"
    lines = [
        f"#### Compared with baseline: {verdict}",
        "",
        "| | Baseline | This run | Change |",
        "| --- | ---: | ---: | ---: |",
        f"| Pass rate | {result.base_pass_rate * 100:.1f}% | {result.head_pass_rate * 100:.1f}% | "
        f"{_signed(result.pass_rate_delta, percent=True)} |",
        f"| Score | {result.base_score:.3f} | {result.head_score:.3f} | {_signed(result.score_delta)} |",
    ]
    if result.regressed or result.fixed:
        lines += ["", "| Task | Baseline | This run |", "| --- | --- | --- |"]
        lines += [f"| `{i.id}` | {i.base_status} | **{i.head_status}** |" for i in result.regressed]
        lines += [f"| `{i.id}` | {i.base_status} | {i.head_status} |" for i in result.fixed]
    if result.added:
        lines += ["", f"New tasks: {', '.join(f'`{t}`' for t in result.added)}"]
    if result.removed:
        lines += ["", f"Removed tasks: {', '.join(f'`{t}`' for t in result.removed)}"]
    if not result.ok:
        lines += ["", *(f"- {reason}" for reason in result.failures)]
    return "\n".join(lines)
