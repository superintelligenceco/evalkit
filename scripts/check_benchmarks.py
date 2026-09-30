"""Fail when a benchmark's median exceeds its budget in benchmarks/baseline.json.

Usage: python scripts/check_benchmarks.py RESULTS.json BASELINE.json

RESULTS.json is the file that `pytest --benchmark-json` writes. Every budgeted benchmark must be
present, so deleting or renaming a benchmark also fails the gate until you update the baseline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    results = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    budgets: dict[str, float] = json.loads(Path(argv[1]).read_text(encoding="utf-8"))["budgets"]
    medians = {bench["name"]: bench["stats"]["median"] for bench in results["benchmarks"]}

    failed = False
    print(f"{'BENCHMARK':40} {'MEDIAN':>10} {'BUDGET':>10}  RESULT")
    for name, budget in sorted(budgets.items()):
        median = medians.get(name)
        if median is None:
            print(f"{name:40} {'missing':>10} {budget * 1e3:>8.2f}ms  FAIL")
            failed = True
            continue
        ok = median <= budget
        failed |= not ok
        print(
            f"{name:40} {median * 1e3:>8.2f}ms {budget * 1e3:>8.2f}ms  "
            f"{'ok' if ok else 'FAIL'} ({median / budget:.0%} of budget)"
        )
    for name in sorted(set(medians) - set(budgets)):
        print(f"{name:40} {medians[name] * 1e3:>8.2f}ms {'none':>10}  add a budget")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
