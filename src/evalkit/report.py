"""Human and machine-readable reports: terminal table, Markdown, JUnit XML, badge JSON."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from evalkit import __version__

_STATUS_LABEL = {"pass": "pass", "fail": "FAIL", "flaky": "FLAKY", "error": "ERROR"}
_ANSI = {"pass": "32", "fail": "31", "flaky": "33", "error": "35", "dim": "2", "bold": "1"}


def _color(text: str, style: str, enabled: bool) -> str:
    return f"\033[{_ANSI[style]}m{text}\033[0m" if enabled else text


def _fmt_ms(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value / 1000:.2f}s" if value >= 1000 else f"{value:.0f}ms"


def _fmt_cost(value: float | None) -> str:
    return "-" if value is None else f"${value:.4f}"


def _one_line(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def failure_detail(task: dict[str, Any]) -> str:
    """The first reason a task failed, for tables and JUnit messages."""
    for run in task["runs"]:
        if run["error"]:
            return str(run["error"])
        for grade in run["grades"]:
            if not grade["passed"]:
                return f"{grade['grader']}: {grade['reason']}"
    return ""


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_table(data: dict[str, Any], *, color: bool = False, width: int = 120) -> str:
    """Render a results dict as a fixed-width terminal table."""
    summary = data["summary"]
    tasks = data["tasks"]
    id_width = max([4, *(len(task["id"]) for task in tasks)])
    id_width = min(id_width, 32)
    header = (
        f"evalkit {data['evalkit_version']}  suite {data['suite']}  target {data['target']}  "
        f"{summary['tasks']} tasks x {data['repeat']} run{'s' if data['repeat'] != 1 else ''}"
    )
    lines = [_color(header, "bold", color), ""]
    columns = f"  {'STATUS':<6}  {'TASK':<{id_width}}  {'SCORE':>5}  {'RUNS':>5}  {'LATENCY':>7}  {'COST':>8}  DETAIL"
    lines.append(_color(columns, "dim", color))
    fixed = len(columns) - len("DETAIL")
    for task in tasks:
        status = task["status"]
        label = _color(f"{_STATUS_LABEL[status]:<6}", status, color)
        runs = f"{task['runs_passed']}/{task['runs_total']}"
        detail = "" if status == "pass" else _one_line(failure_detail(task), max(40, width - fixed))
        task_id = task["id"] if len(task["id"]) <= id_width else task["id"][: id_width - 1] + "~"
        lines.append(
            f"  {label}  {task_id:<{id_width}}  {task['score']:>5.2f}  {runs:>5}  "
            f"{_fmt_ms(task['latency_ms']):>7}  {_fmt_cost(task['cost_usd']):>8}  {detail}".rstrip()
        )
    lines.append("")
    lines.append(summary_line(data))
    verdict = verdict_line(data)
    lines.append(_color(verdict, "pass" if summary["ok"] else "fail", color))
    return "\n".join(lines)


def summary_line(data: dict[str, Any]) -> str:
    s = data["summary"]
    parts = [
        f"{s['passed']}/{s['tasks']} passed ({_pct(s['pass_rate'])})",
        f"score {s['score']:.2f}",
        f"{s['flaky']} flaky",
        f"{s['errored']} errored",
        f"latency p50 {_fmt_ms(s['latency_ms_p50'])} p95 {_fmt_ms(s['latency_ms_p95'])}",
    ]
    if s["cost_usd"] is not None:
        parts.append(f"cost {_fmt_cost(s['cost_usd'])} (spent {_fmt_cost(s['cost_usd_spent'])})")
    parts.append(f"{s['cached_runs']}/{s['runs']} runs cached")
    parts.append(f"{data['duration_s']:.2f}s")
    return ", ".join(parts)


def verdict_line(data: dict[str, Any]) -> str:
    s = data["summary"]
    if s["ok"]:
        return f"PASS: pass rate {_pct(s['pass_rate'])} meets fail_under {_pct(s['fail_under'])}"
    return f"FAIL: pass rate {_pct(s['pass_rate'])} is below fail_under {_pct(s['fail_under'])}"


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(
    data: dict[str, Any], *, comparison: str | None = None, max_rows: int = 50
) -> str:
    """Render a results dict as GitHub-flavored Markdown for job summaries and PR comments."""
    s = data["summary"]
    verdict = "passed" if s["ok"] else "failed"
    lines = [
        f"### evalkit: {data['suite']} {verdict}",
        "",
        f"**{s['passed']}/{s['tasks']} tasks passed** ({_pct(s['pass_rate'])}, "
        f"required {_pct(s['fail_under'])}), score {s['score']:.2f}, target `{data['target']}`, "
        f"{data['repeat']} run{'s' if data['repeat'] != 1 else ''} per task.",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Flaky tasks | {s['flaky']} |",
        f"| Errored tasks | {s['errored']} |",
        f"| Latency p50 / p95 | {_fmt_ms(s['latency_ms_p50'])} / {_fmt_ms(s['latency_ms_p95'])} |",
        f"| Cost (spent) | {_fmt_cost(s['cost_usd'])} ({_fmt_cost(s['cost_usd_spent'])}) |",
        f"| Cached runs | {s['cached_runs']}/{s['runs']} |",
        "",
    ]
    order = {"error": 0, "fail": 1, "flaky": 2, "pass": 3}
    tasks = sorted(data["tasks"], key=lambda task: order[task["status"]])
    lines += ["| Status | Task | Score | Runs | Detail |", "| --- | --- | ---: | ---: | --- |"]
    for task in tasks[:max_rows]:
        detail = "" if task["status"] == "pass" else _one_line(failure_detail(task), 120)
        lines.append(
            f"| {_STATUS_LABEL[task['status']]} | `{task['id']}` | {task['score']:.2f} | "
            f"{task['runs_passed']}/{task['runs_total']} | {_md_escape(detail)} |"
        )
    if len(tasks) > max_rows:
        lines.append(f"\n{len(tasks) - max_rows} more tasks omitted. See the JSON report.")
    if comparison:
        lines += ["", comparison]
    lines += ["", f"<sub>evalkit {data['evalkit_version']}</sub>", ""]
    return "\n".join(lines)


def render_junit(data: dict[str, Any]) -> str:
    """Render a results dict as JUnit XML so CI systems show each task as a test."""
    s = data["summary"]
    suite = ET.Element(
        "testsuite",
        {
            "name": data["suite"],
            "tests": str(s["tasks"]),
            "failures": str(s["failed"] + s["flaky"]),
            "errors": str(s["errored"]),
            "time": f"{data['duration_s']:.3f}",
            "timestamp": data["started_at"],
        },
    )
    props = ET.SubElement(suite, "properties")
    for name, value in (
        ("target", data["target"]),
        ("repeat", data["repeat"]),
        ("seed", data["seed"]),
    ):
        ET.SubElement(props, "property", {"name": name, "value": str(value)})
    for task in data["tasks"]:
        seconds = (task["latency_ms"] or 0) / 1000
        case = ET.SubElement(
            suite,
            "testcase",
            {"classname": data["suite"], "name": task["id"], "time": f"{seconds:.3f}"},
        )
        if task["status"] == "pass":
            continue
        tag = "error" if task["status"] == "error" else "failure"
        detail = failure_detail(task)
        element = ET.SubElement(case, tag, {"message": detail[:500], "type": task["status"]})
        body = []
        for run in task["runs"]:
            body.append(f"run {run['repeat']}: {'pass' if run['passed'] else 'fail'}")
            if run["error"]:
                body.append(f"  error: {run['error']}")
            body.extend(
                f"  {g['grader']}: {'pass' if g['passed'] else 'fail'} {g['reason']}"
                for g in run["grades"]
            )
            body.append(f"  output: {run['output'][:2000]}")
        element.text = "\n".join(body)
    ET.indent(suite)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(suite, encoding="unicode") + "\n"
    )


def badge_json(data: dict[str, Any], *, label: str = "evals") -> dict[str, Any]:
    """A shields.io endpoint badge: https://shields.io/badges/endpoint-badge."""
    s = data["summary"]
    rate = s["pass_rate"]
    if rate >= 1:
        color = "brightgreen"
    elif rate >= 0.9:
        color = "green"
    elif rate >= 0.75:
        color = "yellow"
    elif rate >= 0.5:
        color = "orange"
    else:
        color = "red"
    return {
        "schemaVersion": 1,
        "label": label,
        "message": f"{s['passed']}/{s['tasks']} passed",
        "color": color,
    }


def write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def write_json(path: str | Path, data: Any) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


__all__ = [
    "__version__",
    "badge_json",
    "failure_detail",
    "render_junit",
    "render_markdown",
    "render_table",
    "summary_line",
    "write_json",
    "write_text",
]
