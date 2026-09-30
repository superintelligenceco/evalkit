import xml.etree.ElementTree as ET

import pytest

from evalkit.report import badge_json, failure_detail, render_junit, render_markdown, render_table
from evalkit.runner import run_suite


@pytest.fixture
def data(make_suite):
    suite = make_suite(
        {
            "target": {"provider": "mock", "responses": [{"match": "a", "output": "A"}]},
            "graders": [{"type": "exact"}],
            "tasks": [
                {"id": "good", "input": "a", "expected": "A"},
                {"id": "bad", "input": "b | c", "expected": "B"},
            ],
        }
    )
    return run_suite(suite).to_dict()


def test_table(data):
    table = render_table(data)
    assert "suite t  target mock:mock  2 tasks x 1 run" in table
    assert "pass    good" in table
    assert "FAIL    bad" in table
    assert "exact: expected 'B', got 'b | c'" in table
    assert "1/2 passed (50.0%)" in table
    assert table.rstrip().endswith("FAIL: pass rate 50.0% is below fail_under 100.0%")
    assert "\033[" not in table
    assert "\033[31m" in render_table(data, color=True)


def test_markdown_puts_failures_first_and_escapes_pipes(data):
    md = render_markdown(data, comparison="#### extra")
    assert md.startswith("### evalkit: t failed")
    rows = [
        line for line in md.splitlines() if line.startswith("| FAIL") or line.startswith("| pass")
    ]
    assert rows[0].startswith("| FAIL | `bad`")
    assert "b \\| c" in md
    assert "#### extra" in md


def test_markdown_truncates_rows(data):
    assert "1 more tasks omitted" in render_markdown(data, max_rows=1)


def test_junit_is_valid_xml(data):
    root = ET.fromstring(render_junit(data).split("\n", 1)[1])
    assert root.tag == "testsuite"
    assert root.get("tests") == "2"
    assert root.get("failures") == "1"
    cases = {case.get("name"): case for case in root.iter("testcase")}
    assert cases["good"].find("failure") is None
    failure = cases["bad"].find("failure")
    assert failure is not None
    assert "output: b | c" in (failure.text or "")


@pytest.mark.parametrize(
    ("passed", "total", "color"),
    [
        (10, 10, "brightgreen"),
        (9, 10, "green"),
        (8, 10, "yellow"),
        (5, 10, "orange"),
        (1, 10, "red"),
    ],
)
def test_badge_colors(passed, total, color):
    badge = badge_json(
        {"summary": {"passed": passed, "tasks": total, "pass_rate": passed / total}}, label="x"
    )
    assert badge == {
        "schemaVersion": 1,
        "label": "x",
        "message": f"{passed}/{total} passed",
        "color": color,
    }


def test_failure_detail_prefers_errors():
    task = {"runs": [{"error": "boom", "grades": []}]}
    assert failure_detail(task) == "boom"
    assert failure_detail({"runs": [{"error": None, "grades": [{"passed": True}]}]}) == ""
