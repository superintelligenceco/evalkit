import asyncio
import sys
import time

import pytest

from evalkit.runner import Runner, run_suite, select_tasks

EXACT = [{"type": "exact"}]


def test_runs_tasks_and_grades(make_suite):
    suite = make_suite(
        {
            "target": {"provider": "mock", "responses": [{"match": "a", "output": "A"}]},
            "graders": EXACT,
            "tasks": [
                {"id": "good", "input": "a", "expected": "A"},
                {"id": "bad", "input": "b", "expected": "B"},
            ],
        }
    )
    result = run_suite(suite)
    data = result.to_dict()
    assert [t["status"] for t in data["tasks"]] == ["pass", "fail"]
    assert data["summary"]["pass_rate"] == 0.5
    assert data["summary"]["ok"] is False
    assert data["target"] == "mock:mock"


def test_prompt_template_and_system(make_suite):
    suite = make_suite(
        {
            "system": "sys",
            "prompt": "Q: {{question}} ({{vars.lang}})",
            "tasks": [
                {
                    "id": "t",
                    "vars": {"question": "hi", "lang": "en"},
                    "expected": "Q: hi (en)",
                    "graders": EXACT,
                }
            ],
        }
    )
    assert run_suite(suite).tasks[0].passed


def test_prompt_template_error_marks_task_errored(make_suite):
    suite = make_suite(
        {"prompt": "{{nope}}", "tasks": [{"id": "t", "expected": "x", "graders": EXACT}]}
    )
    task = run_suite(suite).tasks[0]
    assert task.status == "error"
    assert "unknown template variable" in (task.runs[0].error or "")


def test_retries_transient_failures(make_suite):
    suite = make_suite(
        {
            "target": {"provider": "mock", "default": "ok", "fail_times": 2},
            "settings": {"retries": 2},
            "tasks": [{"id": "t", "input": "x", "expected": "ok", "graders": EXACT}],
        }
    )
    run = run_suite(suite, use_cache=False).tasks[0].runs[0]
    assert run.passed
    assert run.attempts == 3


def test_gives_up_after_retries(make_suite):
    suite = make_suite(
        {
            "target": {"provider": "mock", "default": "ok", "fail_times": 5},
            "settings": {"retries": 1},
            "tasks": [{"id": "t", "input": "x", "expected": "ok", "graders": EXACT}],
        }
    )
    task = run_suite(suite, use_cache=False).tasks[0]
    assert task.status == "error"
    assert "after 2 attempts" in (task.runs[0].error or "")


def test_cache_makes_reruns_free(make_suite, tmp_path):
    suite = make_suite(
        {
            "target": {"provider": "mock", "default": "ok", "pricing": {"input_per_mtok": 1e6}},
            "tasks": [{"id": "t", "input": "one two", "expected": "ok", "graders": EXACT}],
        }
    )
    first = run_suite(suite).to_dict()["summary"]
    second = run_suite(suite).to_dict()["summary"]
    assert first["cached_runs"] == 0
    assert first["cost_usd_spent"] == pytest.approx(2.0)
    assert second["cached_runs"] == 1
    assert second["cost_usd"] == pytest.approx(2.0)
    assert second["cost_usd_spent"] == 0
    assert (tmp_path / "cache.sqlite").exists()


def test_no_cache_flag_and_apps_are_not_cached(make_suite, tmp_path):
    suite = make_suite(
        {
            "target": {"provider": "command", "command": [sys.executable, "-c", "print('ok')"]},
            "tasks": [{"id": "t", "input": "x", "expected": "ok", "graders": EXACT}],
        }
    )
    run_suite(suite)
    assert run_suite(suite).to_dict()["summary"]["cached_runs"] == 0
    mock = make_suite({"tasks": [{"id": "t", "input": "x", "expected": "x", "graders": EXACT}]})
    run_suite(mock, use_cache=False)
    assert run_suite(mock, use_cache=False).to_dict()["summary"]["cached_runs"] == 0


def test_repeat_and_flakiness_stats(make_suite):
    suite = make_suite(
        {
            "target": {"provider": "mock", "default": "ok", "flaky": 0.5, "flaky_output": "no"},
            "settings": {"repeat": 20, "task_pass_rate": 0.2},
            "tasks": [{"id": "t", "input": "x", "expected": "ok", "graders": EXACT}],
        }
    )
    task = run_suite(suite).tasks[0]
    assert len(task.runs) == 20
    assert [run.repeat for run in task.runs] == list(range(20))
    assert task.flaky
    assert 0 < task.pass_rate < 1
    assert task.passed


def test_concurrency_runs_in_parallel(make_suite):
    suite = make_suite(
        {
            "target": {"provider": "mock", "default": "ok", "latency_ms": 100},
            "settings": {"concurrency": 10},
            "tasks": [
                {"id": f"t{i}", "input": f"x{i}", "expected": "ok", "graders": EXACT}
                for i in range(10)
            ],
        }
    )
    started = time.perf_counter()
    result = run_suite(suite, use_cache=False)
    assert time.perf_counter() - started < 0.6
    assert all(task.passed for task in result.tasks)


def test_llm_judge_uses_suite_judge_and_caches_it(make_suite):
    suite = make_suite(
        {
            "judge": {"provider": "mock", "default": '{"score": 5, "reason": "good"}'},
            "tasks": [{"id": "t", "input": "x", "graders": [{"type": "llm_judge", "rubric": "r"}]}],
        }
    )
    run = run_suite(suite).tasks[0].runs[0]
    assert run.passed
    assert run.grades[0].reason == "5/5: good"


def test_grader_error_is_reported_per_run(make_suite):
    suite = make_suite(
        {
            "tasks": [
                {
                    "id": "t",
                    "input": "x",
                    "graders": [{"type": "python", "function": "missing.py:f"}],
                }
            ]
        }
    )
    task = run_suite(suite).tasks[0]
    assert task.status == "error"
    assert task.runs[0].error.startswith("grader python: python grader: file not found")


def test_weighted_score(make_suite):
    suite = make_suite(
        {
            "tasks": [
                {
                    "id": "t",
                    "input": "abc",
                    "graders": [
                        {"type": "contains", "value": "a", "weight": 3},
                        {"type": "contains", "value": "z"},
                    ],
                }
            ]
        }
    )
    task = run_suite(suite).tasks[0]
    assert task.score == pytest.approx(0.75)
    assert not task.passed


def test_progress_callback(make_suite):
    seen = []
    suite = make_suite(
        {
            "graders": EXACT,
            "tasks": [{"input": "a", "expected": "a"}, {"input": "b", "expected": "b"}],
        }
    )
    asyncio.run(Runner(suite, progress=lambda task, run: seen.append(task.id)).run())
    assert sorted(seen) == ["task-1", "task-2"]


def test_select_tasks(make_suite):
    suite = make_suite(
        {
            "graders": EXACT,
            "tasks": [
                {"id": "alpha", "input": "a", "expected": "a", "tags": ["x"]},
                {"id": "beta", "input": "b", "expected": "b", "tags": ["y"]},
                {"id": "alphabet", "input": "c", "expected": "c"},
            ],
        }
    )
    ids = lambda tasks: [t.id for t in tasks]  # noqa: E731
    assert ids(select_tasks(suite.tasks, tags=["x", "y"])) == ["alpha", "beta"]
    assert ids(select_tasks(suite.tasks, match="alpha")) == ["alpha", "alphabet"]
    assert ids(select_tasks(suite.tasks, limit=1)) == ["alpha"]


def test_openai_target_against_fake_server(make_suite, fake_server):
    fake_server.fail_next = [503]
    suite = make_suite(
        {
            "target": {
                "provider": "openai",
                "model": "fake",
                "base_url": fake_server.url + "/v1",
                "api_key_env": None,
            },
            "tasks": [
                {
                    "id": "t",
                    "input": "What is 12 squared?",
                    "expected": 144,
                    "graders": [{"type": "numeric"}],
                }
            ],
        }
    )
    run = run_suite(suite).tasks[0].runs[0]
    assert run.passed
    assert run.attempts == 2
    assert (run.input_tokens, run.output_tokens) == (10, 5)
