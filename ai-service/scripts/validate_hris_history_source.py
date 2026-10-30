"""Validate an approved HRIS history CSV without printing employee-level data.

Run from ai-service:
    python scripts/validate_hris_history_source.py --input /secure/path/hris_history.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(AI_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_ROOT))

from app.data.hris_history_source import HrisHistorySourceError, load_governed_hris_history


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a governed effective-dated HRIS history extract.")
    parser.add_argument("--input", type=Path, required=True, help="Path to approved canonical HRIS history CSV.")
    parser.add_argument("--report-json", type=Path, default=None, help="Optional aggregate-only report output.")
    args = parser.parse_args()
    try:
        _, report = load_governed_hris_history(args.input)
    except HrisHistorySourceError as exc:
        report = {"status": "fail", "errors": [str(exc)], "employee_level_values_emitted": False}
        print(json.dumps(report, indent=2))
        return 1

    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(rendered + "\\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
