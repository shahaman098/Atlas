#!/usr/bin/env python3
"""Summarize benchmark CSV success rates."""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "results" / "benchmark-runs.csv"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    if not path.exists():
        raise SystemExit(f"No CSV at {path}")

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        raise SystemExit("CSV has no data rows")

    by_model: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_model[row["model"]].append(row)

    print(f"File: {path}")
    print(f"Total rows: {len(rows)}")
    for model, model_rows in sorted(by_model.items()):
        ok = sum(1 for row in model_rows if row["success"].lower() == "true")
        total = len(model_rows)
        print(f"\n{model}: {ok}/{total} successful ({ok / total:.0%})")
        by_task: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in model_rows:
            by_task[row["task_id"]].append(row)
        for task_id, task_rows in sorted(by_task.items(), key=lambda item: item[0]):
            task_ok = sum(1 for row in task_rows if row["success"].lower() == "true")
            print(f"  task {task_id}: {task_ok}/{len(task_rows)}")


if __name__ == "__main__":
    main()
