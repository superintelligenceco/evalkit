import asyncio
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from evalkit.config import GraderConfig, Task, parse_suite
from evalkit.graders import GradeContext, GraderError, extract_json, run_grader
from evalkit.graders.builtin import parse_number
from evalkit.graders.judge import build_judge_prompt, parse_judge_reply
from evalkit.providers.base import Request, Response

ADAPTER = TypeAdapter(GraderConfig)


def grade(spec, output, *, expected=None, task_vars=None, base_dir=Path("."), call_model=None):
    config = ADAPTER.validate_python(spec)
    task = Task(id="t", input="question", expected=expected, vars=task_vars or {})
    ctx = GradeContext(
        output=output, task=task, prompt="question", base_dir=base_dir, call_model=call_model
    )
    return asyncio.run(run_grader(config, ctx))


# exact -----------------------------------------------------------------------


def test_exact_uses_expected_and_strips():
    assert grade({"type": "exact"}, "  Paris\n", expected="Paris").passed
    result = grade({"type": "exact"}, "paris", expected="Paris")
    assert not result.passed
    assert "expected 'Paris', got 'paris'" in result.reason


def test_exact_options_and_templated_value():
    assert grade({"type": "exact", "ignore_case": True}, "PARIS", expected="paris").passed
    assert not grade({"type": "exact", "strip": False}, "Paris ", expected="Paris").passed
    assert grade({"type": "exact", "value": "{{city}}"}, "Rome", task_vars={"city": "Rome"}).passed
    assert grade({"type": "exact"}, '{"a": 1}', expected={"a": 1}).passed


# contains --------------------------------------------------------------------


def test_contains_all_reports_missing_and_partial_score():
    result = grade({"type": "contains", "value": ["a", "b", "zzz"]}, "a b c")
    assert not result.passed
    assert result.score == pytest.approx(2 / 3)
    assert "'zzz'" in result.reason


def test_contains_any_and_ignore_case():
    assert (
        grade({"type": "contains", "value": ["x", "B"], "mode": "any"}, "abc", expected=None).passed
        is False
    )
    assert grade(
        {"type": "contains", "value": ["x", "B"], "mode": "any", "ignore_case": True}, "abc"
    ).passed
    assert grade({"type": "contains"}, "The answer is 42.", expected=42).passed


# regex -----------------------------------------------------------------------


def test_regex_search_fullmatch_and_ignore_case():
    assert grade({"type": "regex", "pattern": r"\d{3}"}, "code 123 ok").passed
    assert not grade({"type": "regex", "pattern": r"\d{3}", "fullmatch": True}, "code 123").passed
    assert grade({"type": "regex", "pattern": r"\d{3}", "fullmatch": True}, " 123\n").passed
    assert grade({"type": "regex", "pattern": "hello", "ignore_case": True}, "HELLO").passed
    result = grade({"type": "regex", "pattern": "nope"}, "text")
    assert result.reason == "no match for /nope/"


def test_regex_pattern_can_use_templates():
    assert grade({"type": "regex", "pattern": "^{{expected}}$"}, "42", expected=42).passed


# json_schema -----------------------------------------------------------------

SCHEMA = {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}


def test_json_schema_valid_invalid_and_not_json():
    assert grade({"type": "json_schema", "schema": SCHEMA}, '{"name": "x"}').passed
    bad = grade({"type": "json_schema", "schema": SCHEMA}, '{"name": 3}')
    assert not bad.passed
    assert bad.reason.startswith("name: 3 is not of type 'string'")
    assert (
        grade({"type": "json_schema", "schema": SCHEMA}, "no json").reason
        == "output is not valid JSON"
    )


def test_json_schema_extracts_from_fences_and_prose():
    fenced = 'Sure!\n```json\n{"name": "x"}\n```\nDone.'
    prose = 'The record is {"name": "x"} as requested.'
    assert grade({"type": "json_schema", "schema": SCHEMA}, fenced).passed
    assert grade({"type": "json_schema", "schema": SCHEMA}, prose).passed
    assert not grade({"type": "json_schema", "schema": SCHEMA, "extract": False}, prose).passed


def test_json_schema_file_and_errors(tmp_path):
    (tmp_path / "s.yaml").write_text("type: array\nminItems: 2\n")
    assert grade(
        {"type": "json_schema", "schema_file": "s.yaml"}, "[1, 2]", base_dir=tmp_path
    ).passed
    assert not grade(
        {"type": "json_schema", "schema_file": "s.yaml"}, "[1]", base_dir=tmp_path
    ).passed
    with pytest.raises(GraderError, match="cannot read schema file"):
        grade({"type": "json_schema", "schema_file": "missing.json"}, "[]", base_dir=tmp_path)
    with pytest.raises(GraderError, match="invalid JSON schema"):
        grade({"type": "json_schema", "schema": {"type": 5}}, "[]")


def test_extract_json_edge_cases():
    assert extract_json("[1, 2]") == [1, 2]
    assert extract_json('```\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('bad { then {"ok": true}') == {"ok": True}
    with pytest.raises(ValueError, match="no JSON value"):
        extract_json("nothing here")


# numeric ---------------------------------------------------------------------


def test_numeric_tolerances():
    assert grade({"type": "numeric"}, "391", expected=391).passed
    assert not grade({"type": "numeric"}, "390", expected=391).passed
    assert grade({"type": "numeric", "abs_tol": 1}, "390", expected=391).passed
    assert grade({"type": "numeric", "rel_tol": 0.01}, "3.14", expected=3.1416).passed
    assert not grade({"type": "numeric", "rel_tol": 0.0001}, "3.14", expected=3.1416).passed


def test_numeric_picks_last_or_first_number():
    assert grade({"type": "numeric"}, "17 * 23 = 391", expected=391).passed
    assert grade({"type": "numeric", "pick": "first"}, "17 * 23 = 391", expected=17).passed
    assert grade(
        {"type": "numeric", "value": "{{target}}"},
        "It costs $1,250.50",
        task_vars={"target": 1250.5},
    ).passed


def test_numeric_errors():
    assert grade({"type": "numeric"}, "no digits", expected=1).reason == "no number in output"
    with pytest.raises(GraderError, match="is not a number"):
        grade({"type": "numeric"}, "1", expected="abc")


@pytest.mark.parametrize(
    ("text", "value"),
    [("42", 42.0), ("-3.5.", -3.5), ("1e3", 1000.0), ("about .5 of it", 0.5), ("x", None)],
)
def test_parse_number(text, value):
    assert parse_number(text) == value


# python ----------------------------------------------------------------------

GRADERS_PY = """
def boolean(output, context):
    return output == context["expected"]

def scored(output, context, factor=1.0):
    return 0.25 * factor

def tuple_result(output, context):
    return (False, "because")

def dict_result(output, context):
    return {"pass": True, "score": 0.9, "reason": "fine"}

async def async_result(output, context):
    return True

def crash(output, context):
    raise RuntimeError("boom")

def wrong_type(output, context):
    return "yes"

not_callable = 5
"""


@pytest.fixture
def pydir(tmp_path):
    (tmp_path / "g.py").write_text(GRADERS_PY)
    return tmp_path


def test_python_grader_return_types(pydir):
    def py(func, **extra):
        spec = {"type": "python", "function": f"g.py:{func}", **extra}
        return grade(spec, "ok", expected="ok", base_dir=pydir)

    assert py("boolean").passed
    scored = py("scored")
    assert (scored.passed, scored.score) == (False, 0.25)
    assert py("scored", args={"factor": 3}).passed
    assert py("tuple_result").reason == "because"
    assert py("dict_result").score == 0.9
    assert py("async_result").passed
    assert py("boolean", name="custom").grader == "custom"


def test_python_grader_errors(pydir):
    with pytest.raises(GraderError, match="raised RuntimeError"):
        grade({"type": "python", "function": "g.py:crash"}, "x", base_dir=pydir)
    with pytest.raises(GraderError, match="must return bool"):
        grade({"type": "python", "function": "g.py:wrong_type"}, "x", base_dir=pydir)
    with pytest.raises(GraderError, match="is not a function"):
        grade({"type": "python", "function": "g.py:not_callable"}, "x", base_dir=pydir)
    with pytest.raises(GraderError, match="file not found"):
        grade({"type": "python", "function": "nope.py:f"}, "x", base_dir=pydir)
    with pytest.raises(GraderError, match="cannot import module"):
        grade({"type": "python", "function": "no_such_module_xyz:f"}, "x")
    (pydir / "broken.py").write_text("raise ImportError('bad')\n")
    with pytest.raises(GraderError, match=r"importing broken\.py failed"):
        grade({"type": "python", "function": "broken.py:f"}, "x", base_dir=pydir)


def test_python_grader_importable_module(tmp_path, monkeypatch):
    (tmp_path / "my_graders_pkg.py").write_text(
        "def is_upper(output, context):\n    return output.isupper()\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    assert grade({"type": "python", "function": "my_graders_pkg:is_upper"}, "LOUD").passed
    assert not grade({"type": "python", "function": "my_graders_pkg:is_upper"}, "quiet").passed


def test_python_grader_receives_context(pydir):
    assert grade(
        {"type": "python", "function": "g.py:boolean"}, "x", expected="x", base_dir=pydir
    ).passed


# negate and weight -----------------------------------------------------------


def test_negate_inverts_verdict_and_score():
    result = grade({"type": "contains", "value": "sorry", "negate": True}, "Sorry!")
    assert result.passed
    result = grade({"type": "contains", "value": "Sorry", "negate": True}, "Sorry!")
    assert not result.passed
    assert result.grader == "not contains"
    assert result.reason.startswith("negated")


# llm_judge -------------------------------------------------------------------


def judge_caller(reply, seen=None):
    async def call(config, request: Request) -> Response:
        if seen is not None:
            seen.append((config, request))
        return Response(text=reply)

    return call


JUDGE = {"type": "llm_judge", "rubric": "Mentions {{topic}}."}


def test_llm_judge_passes_and_normalizes_score():
    seen = []
    result = grade(
        JUDGE,
        "out",
        task_vars={"topic": "cats"},
        call_model=judge_caller('{"score": 4, "reason": "ok"}', seen),
    )
    assert result.passed
    assert result.score == pytest.approx(0.75)
    assert result.reason == "4/5: ok"
    prompt = seen[0][1].prompt
    assert "Mentions cats." in prompt
    assert "<output>\nout\n</output>" in prompt


def test_llm_judge_fails_below_min_score_and_clamps():
    assert not grade(
        JUDGE, "o", task_vars={"topic": "x"}, call_model=judge_caller('{"score": 3}')
    ).passed
    assert grade(
        {**JUDGE, "min_score": 3},
        "o",
        task_vars={"topic": "x"},
        call_model=judge_caller('{"score": 3}'),
    ).passed
    clamped = grade(JUDGE, "o", task_vars={"topic": "x"}, call_model=judge_caller('{"score": 99}'))
    assert clamped.score == 1.0


def test_llm_judge_unparseable_reply_fails():
    result = grade(JUDGE, "o", task_vars={"topic": "x"}, call_model=judge_caller("I refuse"))
    assert not result.passed
    assert "unparseable judge reply" in result.reason


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ('{"score": 5, "reason": "great"}', (5.0, "great")),
        ('Here you go: ```json\n{"score": 2}\n```', (2.0, "")),
        ("Score: 4. Reasoning follows.", (4.0, "")),
        ('{"score": "3", "reason": "x"}', (3.0, "x")),
    ],
)
def test_parse_judge_reply(reply, expected):
    assert parse_judge_reply(reply) == expected


def test_judge_prompt_includes_reference(tmp_path):
    suite = parse_suite(
        {
            "name": "s",
            "target": {"provider": "mock"},
            "judge": {"provider": "mock"},
            "tasks": [
                {"id": "a", "input": "q", "expected": "ref", "graders": [JUDGE | {"rubric": "r"}]}
            ],
        },
        base_dir=tmp_path,
    )
    task = suite.tasks[0]
    ctx = GradeContext(output="o", task=task, prompt="q", base_dir=tmp_path)
    prompt = build_judge_prompt(task.graders[0], ctx)  # type: ignore[arg-type]
    assert "<reference>\nref\n</reference>" in prompt
    assert '"score": <integer 1-5>' in prompt
