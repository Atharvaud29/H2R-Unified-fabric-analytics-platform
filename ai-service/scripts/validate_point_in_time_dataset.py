"""Build and independently validate the attrition point-in-time feature dataset.

Run from ai-service:
    python scripts/generate_synthetic_employee_history.py
    python scripts/validate_point_in_time_dataset.py --horizon-days 90

Only aggregate diagnostics are printed. Employee-level feature rows are not
written unless a future, explicitly governed export workflow is added.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(AI_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_ROOT))

from app.config import Settings
from app.data.csv_gold import infer_as_of_from_value, load_gold
from app.data.feature_engineering import build_attrition_dataset
from app.data.point_in_time_validation import validate_point_in_time_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate point-in-time attrition feature integrity.")
    parser.add_argument("--sample-data-dir", type=Path, default=None)
    parser.add_argument("--as-of", default=None, help="Optional source cutoff date (YYYY-MM-DD).")
    parser.add_argument("--horizon-days", type=int, default=90)
    parser.add_argument("--report-json", type=Path, default=None, help="Optional aggregate-only JSON report path.")
    args = parser.parse_args()

    sample_data_dir = args.sample_data_dir or Settings().resolved_sample_data_dir()
    as_of = infer_as_of_from_value(args.as_of, sample_data_dir)
    gold = load_gold(sample_data_dir, as_of=as_of)
    dataset = build_attrition_dataset(gold, horizon_days=args.horizon_days)
    report = validate_point_in_time_dataset(dataset, gold, horizon_days=args.horizon_days)

    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(rendered + "\n", encoding="utf-8")

    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
