"""Result objects and their JSON form."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from evalkit import __version__
from evalkit.graders.base import Grade

RESULTS_FORMAT = 1


@dataclass
class RunRecord:
    repeat: int
    output: str
    grades: list[Grade] = field(default_factory=list)
    error: str | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    cached: bool = False
    attempts: int = 1

    @property
    def passed(self) -> bool:
        return self.error is None and all(grade.passed for grade in self.grades)

    @property
    def score(self) -> float:
        if self.error is not None or not self.grades:
            return 0.0
        total = sum(grade.weight for grade in self.grades)
        return sum(grade.score * grade.weight for grade in self.grades) / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "repeat": self.repeat,
            "passed": self.passed,
            "score": round(self.score, 4),
            "output": self.output,
            "error": self.error,
            "latency_ms": None if self.latency_ms is None else round(self.latency_ms, 1),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "cached": self.cached,
            "attempts": self.attempts,
            "grades": [grade.to_dict() for grade in self.grades],
        }


@dataclass
class TaskResult:
    id: str
    prompt: str
    expected: Any = None
    tags: list[str] = field(default_factory=list)
    runs: list[RunRecord] = field(default_factory=list)
    required_pass_rate: float = 1.0

    @property
    def passes(self) -> int:
        return sum(run.passed for run in self.runs)

    @property
    def passed(self) -> bool:
        return bool(self.runs) and self.pass_rate >= self.required_pass_rate - 1e-9

    @property
    def pass_rate(self) -> float:
        return self.passes / len(self.runs) if self.runs else 0.0

    @property
    def score(self) -> float:
        return statistics.fmean(run.score for run in self.runs) if self.runs else 0.0

    @property
    def flaky(self) -> bool:
        return 0 < self.passes < len(self.runs)

    @property
    def errored(self) -> bool:
        return any(run.error is not None for run in self.runs)

    @property
    def cost_usd(self) -> float | None:
        costs = [run.cost_usd for run in self.runs if run.cost_usd is not None]
        return sum(costs) if costs else None

    @property
    def latency_ms(self) -> float | None:
        values = [run.latency_ms for run in self.runs if run.latency_ms is not None]
        return statistics.median(values) if values else None

    @property
    def status(self) -> str:
        if self.passed:
            return "pass"
        if self.flaky:
            return "flaky"
        if self.errored:
            return "error"
        return "fail"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "passed": self.passed,
            "score": round(self.score, 4),
            "pass_rate": round(self.pass_rate, 4),
            "runs_passed": self.passes,
            "runs_total": len(self.runs),
            "tags": self.tags,
            "prompt": self.prompt,
            "expected": self.expected,
            "cost_usd": self.cost_usd,
            "latency_ms": None if self.latency_ms is None else round(self.latency_ms, 1),
            "runs": [run.to_dict() for run in self.runs],
        }


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


@dataclass
class SuiteResult:
    suite: str
    target: str
    started_at: str
    duration_s: float
    repeat: int
    seed: int
    tasks: list[TaskResult] = field(default_factory=list)
    description: str | None = None
    fail_under: float = 1.0

    def summary(self) -> dict[str, Any]:
        runs = [run for task in self.tasks for run in task.runs]
        latencies = [run.latency_ms for run in runs if run.latency_ms is not None]
        costs = [run.cost_usd for run in runs if run.cost_usd is not None]
        fresh_costs = [run.cost_usd for run in runs if run.cost_usd is not None and not run.cached]
        passed = sum(task.passed for task in self.tasks)
        total = len(self.tasks)
        p50 = _percentile(latencies, 50)
        p95 = _percentile(latencies, 95)
        return {
            "tasks": total,
            "passed": passed,
            "failed": sum(task.status == "fail" for task in self.tasks),
            "flaky": sum(task.flaky for task in self.tasks),
            "errored": sum(task.status == "error" for task in self.tasks),
            "pass_rate": round(passed / total, 4) if total else 0.0,
            "score": round(statistics.fmean(t.score for t in self.tasks), 4) if total else 0.0,
            "runs": len(runs),
            "runs_passed": sum(run.passed for run in runs),
            "cached_runs": sum(run.cached for run in runs),
            "cost_usd": round(sum(costs), 6) if costs else None,
            "cost_usd_spent": round(sum(fresh_costs), 6) if costs else None,
            "input_tokens": sum(run.input_tokens or 0 for run in runs),
            "output_tokens": sum(run.output_tokens or 0 for run in runs),
            "latency_ms_p50": None if p50 is None else round(p50, 1),
            "latency_ms_p95": None if p95 is None else round(p95, 1),
            "fail_under": self.fail_under,
            "ok": total > 0 and passed / total >= self.fail_under,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": RESULTS_FORMAT,
            "evalkit_version": __version__,
            "suite": self.suite,
            "description": self.description,
            "target": self.target,
            "started_at": self.started_at,
            "duration_s": round(self.duration_s, 3),
            "repeat": self.repeat,
            "seed": self.seed,
            "summary": self.summary(),
            "tasks": [task.to_dict() for task in self.tasks],
        }
