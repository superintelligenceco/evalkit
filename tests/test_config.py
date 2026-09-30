import json
from pathlib import Path

import pytest

from evalkit.config import (
    ConfigError,
    ExactGrader,
    OpenAIProviderConfig,
    load_suite,
    parse_suite,
    suite_json_schema,
)

EXACT = [{"type": "exact"}]


def _suite(**overrides):
    data = {
        "name": "s",
        "target": {"provider": "mock"},
        "tasks": [{"id": "a", "input": "hi", "expected": "hi", "graders": EXACT}],
    }
    data.update(overrides)
    return data


def test_minimal_suite_loads_with_defaults(tmp_path):
    suite = parse_suite(_suite(), base_dir=tmp_path)
    assert suite.settings.concurrency == 4
    assert suite.settings.repeat == 1
    assert suite.settings.fail_under == 1.0
    assert isinstance(suite.tasks[0].graders[0], ExactGrader)
    assert suite.base_dir == tmp_path


def test_task_ids_are_generated(tmp_path):
    suite = parse_suite(
        _suite(
            tasks=[{"input": "x", "expected": "x"}, {"input": "y", "expected": "y"}], graders=EXACT
        ),
        base_dir=tmp_path,
    )
    assert [t.id for t in suite.tasks] == ["task-1", "task-2"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"tasks": []}, "tasks: List should have at least 1 item"),
        (
            {"tasks": [{"id": "a", "input": "x", "expected": "x"}] * 2, "graders": EXACT},
            "duplicate task id 'a'",
        ),
        ({"tasks": [{"id": "a", "input": "x"}]}, "task 'a' has no graders"),
        (
            {"tasks": [{"id": "a", "input": "x", "graders": EXACT}]},
            "grader 'exact' needs a 'value' or a task-level 'expected'",
        ),
        (
            {"tasks": [{"id": "a", "input": {"q": 1}, "expected": 1, "graders": EXACT}]},
            "'input' must be a string when the suite has no 'prompt'",
        ),
        (
            {
                "tasks": [
                    {"id": "a", "input": "x", "graders": [{"type": "llm_judge", "rubric": "r"}]}
                ]
            },
            "llm_judge needs a 'provider' or a suite-level 'judge'",
        ),
        (
            {"tasks": [{"id": "a", "input": "x", "graders": [{"type": "regex", "pattern": "("}]}]},
            "invalid regex",
        ),
        (
            {"tasks": [{"id": "a", "input": "x", "graders": [{"type": "json_schema"}]}]},
            "set exactly one of 'schema' or 'schema_file'",
        ),
        ({"target": {"provider": "nope"}}, "target"),
        ({"target": {"provider": "openai"}}, "target.openai.model: Field required"),
        ({"surprise": 1}, "surprise: Extra inputs are not permitted"),
        ({"settings": {"concurrency": 0}}, "settings.concurrency"),
        (
            {
                "tasks": [
                    {
                        "id": "a",
                        "input": "x",
                        "graders": [{"type": "python", "function": "nocolon"}],
                    }
                ]
            },
            "expected 'file.py:function'",
        ),
    ],
)
def test_validation_errors_are_readable(tmp_path, overrides, message):
    with pytest.raises(ConfigError) as info:
        parse_suite(_suite(**overrides), base_dir=tmp_path)
    assert message in str(info.value)


def test_non_mapping_document_rejected(tmp_path):
    with pytest.raises(ConfigError, match="expected a mapping"):
        parse_suite(["not", "a", "suite"], base_dir=tmp_path)


def test_load_yaml_file_and_external_tasks(tmp_path):
    (tmp_path / "tasks.jsonl").write_text(
        json.dumps({"id": "a", "input": "x", "expected": "x"})
        + "\n\n"
        + json.dumps({"id": "b", "input": "y", "expected": "y"})
        + "\n"
    )
    (tmp_path / "evals.yaml").write_text(
        "name: s\ntarget: {provider: mock}\ngraders: [{type: exact}]\ntasks: tasks.jsonl\n"
    )
    suite = load_suite(tmp_path / "evals.yaml")
    assert [t.id for t in suite.tasks] == ["a", "b"]
    assert suite.base_dir == tmp_path.resolve()


def test_external_tasks_must_be_a_list(tmp_path):
    (tmp_path / "tasks.json").write_text('{"id": "a"}')
    with pytest.raises(ConfigError, match="expected a list of tasks"):
        parse_suite(_suite(tasks="tasks.json"), base_dir=tmp_path)


def test_missing_and_malformed_files(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_suite(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: [unclosed\n")
    with pytest.raises(ConfigError, match="cannot parse"):
        load_suite(bad)


def test_env_expansion_in_target(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_MODEL", "m-1")
    monkeypatch.delenv("UNSET_BASE", raising=False)
    suite = parse_suite(
        _suite(
            target={
                "provider": "openai",
                "model": "${MY_MODEL}",
                "base_url": "${UNSET_BASE:-http://localhost:9/v1}",
            }
        ),
        base_dir=tmp_path,
    )
    assert isinstance(suite.target, OpenAIProviderConfig)
    assert suite.target.model == "m-1"
    assert suite.target.base_url == "http://localhost:9/v1"


def test_env_expansion_missing_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("NOT_SET_ANYWHERE", raising=False)
    with pytest.raises(ConfigError, match="NOT_SET_ANYWHERE"):
        parse_suite(
            _suite(target={"provider": "openai", "model": "${NOT_SET_ANYWHERE}"}), base_dir=tmp_path
        )


def test_env_is_not_expanded_in_tasks(tmp_path):
    suite = parse_suite(
        _suite(tasks=[{"id": "a", "input": "cost is ${PRICE}", "expected": "x", "graders": EXACT}]),
        base_dir=tmp_path,
    )
    assert suite.tasks[0].input == "cost is ${PRICE}"


def test_json_schema_export_is_valid():
    import jsonschema

    schema = suite_json_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    assert "base_dir" not in json.dumps(schema)
    assert "llm_judge" in json.dumps(schema)


@pytest.mark.parametrize("path", sorted(Path(__file__).parent.parent.glob("examples/*/evals.yaml")))
def test_examples_validate(path, monkeypatch):
    load_suite(path)
