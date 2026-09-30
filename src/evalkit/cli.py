"""Command-line interface: ``evalkit run | compare | validate | init | schema | cache``."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from evalkit import __version__
from evalkit.cache import ResponseCache
from evalkit.compare import (
    CompareError,
    compare,
    load_results,
    render_comparison_markdown,
    render_comparison_text,
)
from evalkit.config import ConfigError, load_suite, suite_json_schema
from evalkit.report import (
    badge_json,
    render_junit,
    render_markdown,
    render_table,
    write_json,
    write_text,
)
from evalkit.results import RunRecord, TaskResult
from evalkit.runner import Runner, select_tasks

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

INIT_SUITE = """\
# evalkit suite. Reference: https://github.com/superintelligenceco/evalkit#suite-file-reference
name: my-first-suite
description: Replace the mock target with your model or app.

# The thing under test. The mock provider answers from regex rules so this runs offline.
# Swap in `provider: openai` (any OpenAI-compatible API), `anthropic`, `command`, or `http`.
target:
  provider: mock
  responses:
    - match: "capital of France"
      output: "Paris"
    - match: "2 \\\\+ 2"
      output: "The answer is 4."
    - match: "JSON"
      output: '{"name": "Ada Lovelace", "born": 1815}'

prompt: "{{question}}"

tasks:
  - id: capital
    vars: {question: "What is the capital of France? Answer with one word."}
    expected: Paris
    graders:
      - type: exact

  - id: arithmetic
    vars: {question: "What is 2 + 2?"}
    expected: 4
    graders:
      - type: numeric

  - id: structured
    vars: {question: "Return a JSON object with name and born for Ada Lovelace."}
    graders:
      - type: json_schema
        schema:
          type: object
          required: [name, born]
          properties:
            name: {type: string}
            born: {type: integer}
"""


def _stderr_is_tty() -> bool:
    return sys.stderr.isatty() and os.environ.get("TERM") != "dumb"


def _use_color(stream: TextIO, disabled: bool) -> bool:
    if disabled or os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return stream.isatty()


class _Progress:
    def __init__(self, total: int, enabled: bool) -> None:
        self.total = total
        self.done = 0
        self.failed = 0
        self.enabled = enabled

    def __call__(self, task: TaskResult, run: RunRecord) -> None:
        self.done += 1
        self.failed += not run.passed
        if self.enabled:
            sys.stderr.write(f"\r  running {self.done}/{self.total}  ({self.failed} failing)   ")
            sys.stderr.flush()

    def finish(self) -> None:
        if self.enabled and self.done:
            sys.stderr.write("\r" + " " * 48 + "\r")
            sys.stderr.flush()


def _cmd_run(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    if args.fail_under is not None:
        suite.settings.fail_under = args.fail_under
    tasks = select_tasks(suite.tasks, tags=args.tag or (), match=args.match, limit=args.limit)
    if not tasks:
        print("error: no tasks match the given filters", file=sys.stderr)
        return EXIT_USAGE
    repeat = args.repeat or suite.settings.repeat
    progress = _Progress(len(tasks) * repeat, enabled=_stderr_is_tty() and not args.quiet)
    runner = Runner(
        suite,
        use_cache=False if args.no_cache else None,
        cache_path=args.cache_path,
        concurrency=args.concurrency,
        repeat=args.repeat,
        seed=args.seed,
        tasks=tasks,
        progress=progress,
    )
    result = asyncio.run(runner.run())
    progress.finish()
    data = result.to_dict()
    exit_code = EXIT_OK if data["summary"]["ok"] else EXIT_FAILED

    comparison_md = None
    comparison_text = None
    if args.baseline:
        comparison = compare(
            load_results(args.baseline), data, threshold=args.threshold, strict=args.strict
        )
        data["comparison"] = comparison.to_dict()
        comparison_text = render_comparison_text(comparison)
        comparison_md = render_comparison_markdown(comparison)
        if not comparison.ok:
            exit_code = EXIT_FAILED

    if args.output:
        write_json(args.output, data)
    if args.junit:
        write_text(args.junit, render_junit(data))
    if args.markdown:
        write_text(args.markdown, render_markdown(data, comparison=comparison_md))
    if args.badge:
        write_json(args.badge, badge_json(data, label=args.badge_label))

    if args.format == "json":
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif not args.quiet:
        width = shutil.get_terminal_size((120, 24)).columns
        print(render_table(data, color=_use_color(sys.stdout, args.no_color), width=width))
        if comparison_text:
            print()
            print(f"compared with {args.baseline}:")
            print(comparison_text)
    return exit_code


def _cmd_compare(args: argparse.Namespace) -> int:
    comparison = compare(
        load_results(args.base),
        load_results(args.head),
        threshold=args.threshold,
        strict=args.strict,
    )
    if args.format == "json":
        print(json.dumps(comparison.to_dict(), indent=2))
    elif args.format == "markdown":
        print(render_comparison_markdown(comparison))
    else:
        print(render_comparison_text(comparison))
    return EXIT_OK if comparison.ok else EXIT_FAILED


def _cmd_validate(args: argparse.Namespace) -> int:
    status = EXIT_OK
    for path in args.suites:
        try:
            suite = load_suite(path)
        except ConfigError as exc:
            print(exc, file=sys.stderr)
            status = EXIT_USAGE
            continue
        graders = sum(len(suite.graders_for(task)) for task in suite.tasks)
        print(
            f"{path}: ok ({len(suite.tasks)} tasks, {graders} grader checks, target {suite.target.provider})"
        )
    return status


def _cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.directory) / "evals.yaml"
    if target.exists() and not args.force:
        print(f"error: {target} already exists (use --force to overwrite)", file=sys.stderr)
        return EXIT_USAGE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(INIT_SUITE, encoding="utf-8")
    print(f"wrote {target}\nnext: evalkit run {target}")
    return EXIT_OK


def _cmd_schema(args: argparse.Namespace) -> int:
    print(json.dumps(suite_json_schema(), indent=2))
    return EXIT_OK


def _cmd_cache(args: argparse.Namespace) -> int:
    path = Path(args.cache_path)
    if not path.exists():
        print(f"no cache at {path}")
        return EXIT_OK
    cache = ResponseCache(path)
    try:
        if args.action == "clear":
            print(f"deleted {cache.clear()} cached responses from {path}")
        else:
            stats: dict[str, Any] = cache.stats()
            print(
                f"{stats['path']}: {stats['entries']} responses, {stats['text_bytes']} bytes of text"
            )
            for provider, count in stats["by_provider"].items():
                print(f"  {provider}: {count}")
    finally:
        cache.close()
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evalkit",
        description="Evals as code for LLM apps and agents.",
    )
    parser.add_argument("--version", action="version", version=f"evalkit {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    run = sub.add_parser("run", help="run a suite and report results")
    run.add_argument("suite", help="path to the suite YAML file")
    out = run.add_argument_group("outputs")
    out.add_argument("-o", "--output", metavar="PATH", help="write the full results JSON")
    out.add_argument("--junit", metavar="PATH", help="write JUnit XML")
    out.add_argument("--markdown", metavar="PATH", help="write a Markdown summary")
    out.add_argument("--badge", metavar="PATH", help="write a shields.io endpoint badge JSON")
    out.add_argument("--badge-label", default="evals", help="badge label (default: evals)")
    out.add_argument("--format", choices=["table", "json"], default="table", help="stdout format")
    out.add_argument("-q", "--quiet", action="store_true", help="print nothing on stdout")
    out.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    sel = run.add_argument_group("selection")
    sel.add_argument("-t", "--tag", action="append", help="only tasks with this tag (repeatable)")
    sel.add_argument("-k", "--match", metavar="TEXT", help="only tasks whose id contains TEXT")
    sel.add_argument("--limit", type=int, metavar="N", help="run at most N tasks")
    ex = run.add_argument_group("execution")
    ex.add_argument("-j", "--concurrency", type=int, metavar="N", help="parallel requests")
    ex.add_argument("-n", "--repeat", type=int, metavar="N", help="runs per task")
    ex.add_argument("--seed", type=int, help="base seed")
    ex.add_argument("--no-cache", action="store_true", help="ignore and do not write the cache")
    ex.add_argument("--cache-path", metavar="PATH", help="SQLite cache location")
    gate = run.add_argument_group("gating")
    gate.add_argument("--fail-under", type=float, metavar="RATE", help="minimum pass rate, 0 to 1")
    gate.add_argument("--baseline", metavar="PATH", help="results JSON to compare against")
    gate.add_argument("--threshold", type=float, default=0.0, help="allowed drop vs baseline")
    gate.add_argument("--strict", action="store_true", help="fail if any task regresses")
    run.set_defaults(func=_cmd_run)

    cmp = sub.add_parser("compare", help="diff two results files and gate on regressions")
    cmp.add_argument("base", help="baseline results JSON")
    cmp.add_argument("head", help="new results JSON")
    cmp.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="allowed drop in pass rate or score, as a fraction (0.05 = 5 points)",
    )
    cmp.add_argument("--strict", action="store_true", help="fail if any single task regresses")
    cmp.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    cmp.set_defaults(func=_cmd_compare)

    val = sub.add_parser("validate", help="check suite files without running them")
    val.add_argument("suites", nargs="+", metavar="SUITE")
    val.set_defaults(func=_cmd_validate)

    init = sub.add_parser("init", help="write a starter evals.yaml")
    init.add_argument("directory", nargs="?", default=".")
    init.add_argument("--force", action="store_true", help="overwrite an existing file")
    init.set_defaults(func=_cmd_init)

    schema = sub.add_parser("schema", help="print the suite JSON Schema (for editor support)")
    schema.set_defaults(func=_cmd_schema)

    cache = sub.add_parser("cache", help="inspect or clear the response cache")
    cache.add_argument("action", choices=["stats", "clear"])
    cache.add_argument("--cache-path", default=".evalkit/cache.sqlite", metavar="PATH")
    cache.set_defaults(func=_cmd_cache)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ConfigError, CompareError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:  # pragma: no cover
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
