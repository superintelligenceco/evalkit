"""Run the README quickstart exactly as written, so the docs can't drift from the tool."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from evalkit.cli import main

README = Path(__file__).resolve().parent.parent / "README.md"


def quickstart_commands() -> list[list[str]]:
    text = README.read_text(encoding="utf-8")
    section = text.split("\n## Quickstart\n", 1)[1].split("\n## ", 1)[0]
    block = re.search(r"```sh\n(.*?)```", section, re.DOTALL)
    assert block, "the Quickstart section has no sh code block"
    commands = [shlex.split(line) for line in block.group(1).splitlines() if line.strip()]
    assert commands, "the Quickstart code block is empty"
    return commands


def test_quickstart_commands_all_call_evalkit() -> None:
    assert all(cmd[0] == "evalkit" for cmd in quickstart_commands())


def test_readme_quickstart_runs_offline_and_passes(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NO_COLOR", "1")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    for cmd in quickstart_commands():
        try:
            code = main(cmd[1:])
        except SystemExit as exit_:  # pragma: no cover - argparse exits on --help and --version
            code = exit_.code
        assert code == 0, f"`{shlex.join(cmd)}` exited with {code}"
    out = capsys.readouterr().out
    assert "PASS" in out
    assert (tmp_path / "evals.yaml").is_file()


EXAMPLE_SUITES = sorted(p.parent.name for p in (README.parent / "examples").glob("*/evals.yaml"))


@pytest.mark.parametrize("suite", EXAMPLE_SUITES)
def test_readme_links_every_example(suite: str) -> None:
    assert f"examples/{suite}" in README.read_text(encoding="utf-8")
