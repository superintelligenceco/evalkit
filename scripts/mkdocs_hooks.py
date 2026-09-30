"""MkDocs hooks that generate reference pages from the evalkit source.

`<!-- evalkit:cli -->` expands to the `--help` output of every command, and
`<!-- evalkit:schema -->` expands to the suite JSON Schema. The reference therefore can't drift
from the code.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from evalkit.cli import build_parser
from evalkit.config import suite_json_schema


def _cli_reference() -> str:
    os.environ["COLUMNS"] = "100"
    parser = build_parser()
    parts = ["## evalkit", "", "```text", parser.format_help().rstrip(), "```", ""]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                parts += [
                    f"## evalkit {name}",
                    "",
                    "```text",
                    sub.format_help().rstrip(),
                    "```",
                    "",
                ]
    return "\n".join(parts)


def _schema_reference() -> str:
    schema = json.dumps(suite_json_schema(), indent=2)
    return f"```json\n{schema}\n```\n"


def on_page_markdown(markdown: str, **_: Any) -> str:
    if "<!-- evalkit:cli -->" in markdown:
        markdown = markdown.replace("<!-- evalkit:cli -->", _cli_reference())
    if "<!-- evalkit:schema -->" in markdown:
        markdown = markdown.replace("<!-- evalkit:schema -->", _schema_reference())
    return markdown
