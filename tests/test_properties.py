"""Property-based tests for the pure core: templating, number parsing, JSON extraction, compare."""

from __future__ import annotations

import json
import string
from typing import Any

from hypothesis import assume, given
from hypothesis import strategies as st

from evalkit.compare import compare
from evalkit.graders.base import extract_json
from evalkit.graders.builtin import parse_number
from evalkit.results import _percentile
from evalkit.templating import has_placeholders, render, render_value

names = st.from_regex(r"[A-Za-z_][A-Za-z0-9_]{0,10}", fullmatch=True)
plain_text = st.text(alphabet=st.characters(blacklist_characters="{}"), max_size=60)
json_scalars = st.none() | st.booleans() | st.integers() | st.text(max_size=20)
json_values = st.recursive(
    json_scalars | st.floats(allow_nan=False, allow_infinity=False),
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=8), children, max_size=4)
    ),
    max_leaves=12,
)


# templating ------------------------------------------------------------------


@given(plain_text)
def test_render_leaves_text_without_placeholders_alone(text: str) -> None:
    assert not has_placeholders(text)
    assert render(text, {}) == text


@given(names, plain_text, plain_text, st.text(max_size=30))
def test_render_substitutes_string_values(name: str, before: str, after: str, value: str) -> None:
    assert render(f"{before}{{{{ {name} }}}}{after}", {name: value}) == before + value + after


@given(names, json_values)
def test_single_placeholder_keeps_the_value_type(name: str, value: Any) -> None:
    assert render_value(f"{{{{{name}}}}}", {name: value}) == value


@given(names, st.lists(st.integers(), min_size=1, max_size=5), st.data())
def test_dotted_paths_index_into_lists(name: str, items: list[int], data: st.DataObject) -> None:
    index = data.draw(st.integers(min_value=0, max_value=len(items) - 1))
    context = {"vars": {name: items}}
    assert render_value(f"{{{{ vars.{name}.{index} }}}}", context) == items[index]


# parse_number ----------------------------------------------------------------


@given(st.integers(min_value=-(10**12), max_value=10**12))
def test_parse_number_reads_integers_with_thousands_separators(n: int) -> None:
    assert parse_number(f"The total is {n:,}.") == n
    assert parse_number(str(n)) == n


@given(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e9, max_value=1e9))
def test_parse_number_round_trips_a_bare_float(x: float) -> None:
    assert parse_number(repr(x)) == x


@given(st.integers(0, 10**6), st.integers(0, 10**6))
def test_parse_number_picks_first_or_last(a: int, b: int) -> None:
    text = f"{a} then {b}"
    assert parse_number(text, "first") == a
    assert parse_number(text, "last") == b


# extract_json ----------------------------------------------------------------

json_objects = st.dictionaries(st.text(string.ascii_letters, max_size=8), json_values, max_size=5)


@given(json_objects)
def test_extract_json_finds_an_object_in_a_code_fence(obj: dict[str, Any]) -> None:
    reply = f"Here you go:\n```json\n{json.dumps(obj, indent=2)}\n```\nAnything else?"
    assert extract_json(reply) == obj


@given(json_objects, st.text(alphabet=string.ascii_letters + " .,:", max_size=40))
def test_extract_json_finds_an_object_after_prose(obj: dict[str, Any], prose: str) -> None:
    assert extract_json(f"{prose} {json.dumps(obj)}") == obj


# compare ---------------------------------------------------------------------


@st.composite
def results(draw: st.DrawFn, ids: list[str] | None = None) -> dict[str, Any]:
    task_ids = (
        ids if ids is not None else draw(st.lists(names, min_size=1, max_size=8, unique=True))
    )
    tasks = []
    for task_id in task_ids:
        passed = draw(st.booleans())
        score = draw(st.floats(0, 1)) if not passed else draw(st.floats(0.5, 1))
        tasks.append(
            {
                "id": task_id,
                "passed": passed,
                "status": "pass" if passed else "FAIL",
                "score": score,
            }
        )
    pass_rate = sum(t["passed"] for t in tasks) / len(tasks)
    score = sum(t["score"] for t in tasks) / len(tasks)
    return {"summary": {"pass_rate": pass_rate, "score": score}, "tasks": tasks}


@given(results())
def test_a_run_never_regresses_against_itself(run: dict[str, Any]) -> None:
    result = compare(run, run, strict=True)
    assert result.ok
    assert not result.regressed
    assert not result.fixed
    assert not result.added
    assert not result.removed


@given(st.lists(names, min_size=1, max_size=8, unique=True), st.data())
def test_regressions_one_way_are_fixes_the_other_way(ids: list[str], data: st.DataObject) -> None:
    base = data.draw(results(ids))
    head = data.draw(results(ids))
    forward = compare(base, head)
    backward = compare(head, base)
    assert {t.id for t in forward.regressed} == {t.id for t in backward.fixed}
    assert {t.id for t in forward.fixed} == {t.id for t in backward.regressed}


@given(st.lists(names, min_size=1, max_size=8, unique=True), st.data())
def test_a_threshold_of_one_only_fails_in_strict_mode(ids: list[str], data: st.DataObject) -> None:
    base = data.draw(results(ids))
    head = data.draw(results(ids))
    assert compare(base, head, threshold=1.0).ok
    strict = compare(base, head, threshold=1.0, strict=True)
    assert strict.ok == (not strict.regressed)


# percentiles -----------------------------------------------------------------


@given(st.lists(st.floats(0, 1e6), min_size=1, max_size=50), st.floats(0, 100))
def test_percentile_is_a_member_between_min_and_max(values: list[float], pct: float) -> None:
    value = _percentile(values, pct)
    assert value in values
    assert min(values) <= value <= max(values)


@given(st.lists(st.floats(0, 1e6), min_size=1, max_size=50))
def test_percentile_is_monotonic(values: list[float]) -> None:
    p50, p95 = _percentile(values, 50), _percentile(values, 95)
    assume(p50 is not None and p95 is not None)
    assert p50 <= p95
