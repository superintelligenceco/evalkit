"""Benchmarks for the hot paths. Run with `make bench`; CI gates them against baseline.json."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from evalkit.compare import compare
from evalkit.config import load_suite, parse_suite
from evalkit.report import render_junit, render_markdown, render_table
from evalkit.runner import run_suite
from evalkit.templating import render

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
TASKS = 200


def big_suite_payload() -> dict[str, Any]:
    return {
        "name": "bench",
        "target": {
            "provider": "mock",
            "responses": [{"match": r"task (\d+)", "output": "The answer is 42, see Billing."}],
        },
        "prompt": "Solve task {{ n }} for {{ vars.user }}.",
        "graders": [
            {"type": "contains", "value": ["Billing"]},
            {"type": "regex", "pattern": r"answer is \d+"},
            {"type": "numeric", "value": 42},
        ],
        "settings": {"cache": False, "concurrency": 16},
        "tasks": [{"id": f"t{i}", "vars": {"n": i, "user": f"user{i}"}} for i in range(TASKS)],
    }


def results(flip_every: int) -> dict[str, Any]:
    tasks = [
        {
            "id": f"t{i}",
            "passed": i % flip_every != 0,
            "status": "pass" if i % flip_every else "FAIL",
            "score": 1.0 if i % flip_every else 0.5,
        }
        for i in range(2000)
    ]
    passed = sum(t["passed"] for t in tasks)
    return {
        "summary": {"pass_rate": passed / len(tasks), "score": 0.9},
        "tasks": tasks,
    }


def test_bench_load_example_suite(benchmark: Any) -> None:
    suite = benchmark(load_suite, EXAMPLES / "support-bot" / "evals.yaml")
    assert suite.tasks


def test_bench_render_template(benchmark: Any) -> None:
    context = {"vars": {"city": "Paris", "items": list(range(10))}, "input": "hi"}
    text = "Tell {{ input }} about {{ vars.city }} and item {{ vars.items.3 }}. " * 20
    out = benchmark(render, text, context)
    assert "Paris" in out


def test_bench_run_200_tasks_on_mock(benchmark: Any, tmp_path: Path) -> None:
    suite = parse_suite(big_suite_payload(), base_dir=tmp_path)
    result = benchmark.pedantic(run_suite, args=(suite,), rounds=5, iterations=1)
    assert result.to_dict()["summary"]["passed"] == TASKS


def test_bench_compare_2000_tasks(benchmark: Any) -> None:
    base, head = results(7), results(5)
    outcome = benchmark(compare, base, head, strict=True)
    assert outcome.regressed


@pytest.fixture(scope="module")
def run_data(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    suite = parse_suite(big_suite_payload(), base_dir=tmp_path_factory.mktemp("bench"))
    return run_suite(suite).to_dict()


def test_bench_render_reports(benchmark: Any, run_data: dict[str, Any]) -> None:
    def render_all() -> int:
        return (
            len(render_table(run_data))
            + len(render_markdown(run_data))
            + len(render_junit(run_data))
        )

    assert benchmark(render_all) > 0
