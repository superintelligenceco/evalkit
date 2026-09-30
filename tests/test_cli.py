"""End-to-end tests through the command-line entry point."""

import json
import shutil

import pytest

from evalkit.cli import main

from .conftest import EXAMPLES


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NO_COLOR", "1")


def test_version(capsys):
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert capsys.readouterr().out.startswith("evalkit ")


def test_quickstart_example_passes_and_writes_every_output(tmp_path, capsys):
    code = main(
        [
            "run",
            str(EXAMPLES / "quickstart" / "evals.yaml"),
            "-o",
            "out/results.json",
            "--junit",
            "out/junit.xml",
            "--markdown",
            "out/summary.md",
            "--badge",
            "out/badge.json",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "6/6 passed (100.0%)" in out
    results = json.loads((tmp_path / "out/results.json").read_text())
    assert results["summary"]["ok"] is True
    assert results["format"] == 1
    assert (tmp_path / "out/junit.xml").read_text().startswith("<?xml")
    assert "### evalkit: quickstart passed" in (tmp_path / "out/summary.md").read_text()
    assert json.loads((tmp_path / "out/badge.json").read_text())["message"] == "6/6 passed"
    assert (tmp_path / ".evalkit/cache.sqlite").exists()


def test_support_bot_example_runs_a_command_target(capsys):
    code = main(["run", str(EXAMPLES / "support-bot" / "evals.yaml"), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    statuses = {task["id"]: task["status"] for task in data["tasks"]}
    assert statuses["cancel-subscription"] == "fail"
    assert sum(status == "pass" for status in statuses.values()) == 7


def test_flaky_example_reports_flaky_tasks(capsys):
    assert main(["run", str(EXAMPLES / "flaky" / "evals.yaml"), "--format", "json"]) == 0
    summary = json.loads(capsys.readouterr().out)["summary"]
    assert summary["runs"] == 30
    assert summary["flaky"] >= 1


def test_fail_under_sets_exit_code(capsys):
    suite = str(EXAMPLES / "support-bot" / "evals.yaml")
    assert main(["run", suite, "--fail-under", "1", "-q"]) == 1
    assert capsys.readouterr().out == ""


def test_openai_compatible_example_against_fake_server(fake_server, monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_BASE_URL", fake_server.url + "/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    code = main(["run", str(EXAMPLES / "openai-compatible" / "evals.yaml"), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0, data
    assert data["summary"]["passed"] == 4
    assert data["target"] == "openai:gpt-4o-mini"
    paths = {request["path"] for request in fake_server.requests}
    assert paths == {"/v1/chat/completions"}
    first_count = len(fake_server.requests)
    # A rerun is served from the cache and sends no requests.
    main(["run", str(EXAMPLES / "openai-compatible" / "evals.yaml"), "-q"])
    assert len(fake_server.requests) == first_count


def test_baseline_gate_and_compare_command(tmp_path, capsys):
    suite_dir = tmp_path / "suite"
    shutil.copytree(EXAMPLES / "support-bot", suite_dir)
    suite = str(suite_dir / "evals.yaml")
    assert main(["run", suite, "-o", "base.json", "-q"]) == 0

    # Break the bot's order lookup: the order tasks regress.
    bot = suite_dir / "bot.py"
    bot.write_text(bot.read_text().replace('"A1001": "shipped"', '"A1001": "lost"'))
    assert (
        main(["run", suite, "-o", "head.json", "--baseline", "base.json", "--fail-under", "0"]) == 1
    )
    out = capsys.readouterr().out
    assert "regressed (1):" in out
    assert "order-status: pass -> fail" in out

    assert main(["compare", "base.json", "head.json"]) == 1
    assert "REGRESSION: pass rate dropped 12.5 points" in capsys.readouterr().out
    assert main(["compare", "base.json", "head.json", "--threshold", "0.2"]) == 0
    capsys.readouterr()
    assert main(["compare", "base.json", "head.json", "--threshold", "0.2", "--strict"]) == 1
    capsys.readouterr()
    assert main(["compare", "base.json", "head.json", "--format", "json"]) == 1
    assert json.loads(capsys.readouterr().out)["regressed"][0]["id"] == "order-status"
    assert main(["compare", "base.json", "head.json", "--format", "markdown"]) == 1
    assert "**fail**" in capsys.readouterr().out


def test_selection_flags(capsys):
    suite = str(EXAMPLES / "support-bot" / "evals.yaml")
    assert main(["run", suite, "-t", "orders", "--format", "json"]) == 0
    ids = [task["id"] for task in json.loads(capsys.readouterr().out)["tasks"]]
    assert ids == ["order-status", "unknown-order"]
    assert main(["run", suite, "-k", "nothing-matches"]) == 2
    assert "no tasks match" in capsys.readouterr().err


def test_repeat_and_no_cache(capsys):
    suite = str(EXAMPLES / "quickstart" / "evals.yaml")
    assert main(["run", suite, "-n", "3", "--no-cache", "--format", "json"]) == 0
    summary = json.loads(capsys.readouterr().out)["summary"]
    assert summary["runs"] == 18
    assert summary["cached_runs"] == 0


def test_validate(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\ntarget: {provider: mock}\ntasks: []\n")
    assert main(["validate", str(EXAMPLES / "quickstart" / "evals.yaml")]) == 0
    assert "ok (6 tasks" in capsys.readouterr().out
    assert main(["validate", str(bad)]) == 2
    assert "tasks: List should have at least 1 item" in capsys.readouterr().err


def test_init_writes_a_suite_that_passes(tmp_path, capsys):
    assert main(["init", "starter"]) == 0
    assert main(["init", "starter"]) == 2
    capsys.readouterr()
    assert main(["run", "starter/evals.yaml", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["passed"] == 3


def test_schema_command(capsys):
    assert main(["schema"]) == 0
    assert json.loads(capsys.readouterr().out)["title"] == "evalkit suite"


def test_cache_command(capsys):
    assert main(["cache", "stats"]) == 0
    assert "no cache" in capsys.readouterr().out
    main(["run", str(EXAMPLES / "quickstart" / "evals.yaml"), "-q"])
    assert main(["cache", "stats"]) == 0
    assert "6 responses" in capsys.readouterr().out
    assert main(["cache", "clear"]) == 0
    assert "deleted 6" in capsys.readouterr().out


def test_config_errors_exit_2(tmp_path, capsys):
    assert main(["run", str(tmp_path / "missing.yaml")]) == 2
    assert "error: cannot read" in capsys.readouterr().err
    assert main(["compare", "a.json", "b.json"]) == 2
