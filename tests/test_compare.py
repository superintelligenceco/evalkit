import json

import pytest

from evalkit.compare import (
    CompareError,
    compare,
    load_results,
    render_comparison_markdown,
    render_comparison_text,
)


def results(statuses, scores=None):
    scores = scores or {}
    tasks = []
    for task_id, status in statuses.items():
        passed = status == "pass"
        tasks.append(
            {
                "id": task_id,
                "status": status,
                "passed": passed,
                "score": scores.get(task_id, float(passed)),
            }
        )
    total = len(tasks)
    return {
        "summary": {
            "pass_rate": sum(t["passed"] for t in tasks) / total,
            "score": sum(t["score"] for t in tasks) / total,
        },
        "tasks": tasks,
    }


def test_identical_results_are_ok():
    data = results({"a": "pass", "b": "fail"})
    result = compare(data, data)
    assert result.ok
    assert not result.regressed
    assert "OK: no regression" in render_comparison_text(result)


def test_regression_beyond_threshold_fails():
    base = results({"a": "pass", "b": "pass", "c": "pass", "d": "pass"})
    head = results({"a": "pass", "b": "pass", "c": "pass", "d": "fail"})
    result = compare(base, head)
    assert not result.ok
    assert [c.id for c in result.regressed] == ["d"]
    assert result.pass_rate_delta == pytest.approx(-0.25)
    assert any("pass rate dropped 25.0 points" in f for f in result.failures)
    assert compare(base, head, threshold=0.3).ok


def test_strict_fails_on_any_regressed_task_even_if_rate_holds():
    base = results({"a": "pass", "b": "fail"})
    head = results({"a": "fail", "b": "pass"})
    assert compare(base, head).ok
    strict = compare(base, head, strict=True)
    assert not strict.ok
    assert [c.id for c in strict.fixed] == ["b"]
    assert "1 task(s) regressed (strict mode)" in strict.failures


def test_score_changes_added_and_removed():
    base = results({"a": "fail", "gone": "pass"}, {"a": 0.2})
    head = results({"a": "fail", "new": "pass"}, {"a": 0.6})
    result = compare(base, head, threshold=1)
    assert [c.id for c in result.score_changes] == ["a"]
    assert result.added == ["new"]
    assert result.removed == ["gone"]
    text = render_comparison_text(result)
    assert "new tasks (1): new" in text
    assert "removed tasks (1): gone" in text
    assert result.to_dict()["added"] == ["new"]


def test_score_drop_alone_fails():
    base = results({"a": "fail"}, {"a": 0.9})
    head = results({"a": "fail"}, {"a": 0.5})
    result = compare(base, head, threshold=0.1)
    assert any(f.startswith("score dropped 0.400") for f in result.failures)


def test_markdown_rendering():
    base = results({"a": "pass", "b": "fail"})
    head = results({"a": "fail", "b": "pass", "c": "pass"})
    md = render_comparison_markdown(compare(base, head, strict=True))
    assert md.startswith("#### Compared with baseline: regression")
    assert "| `a` | pass | **fail** |" in md
    assert "New tasks: `c`" in md


def test_load_results_errors(tmp_path):
    with pytest.raises(CompareError, match="cannot read"):
        load_results(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    with pytest.raises(CompareError, match="not valid JSON"):
        load_results(bad)
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"hello": 1}))
    with pytest.raises(CompareError, match="not an evalkit results file"):
        load_results(other)
