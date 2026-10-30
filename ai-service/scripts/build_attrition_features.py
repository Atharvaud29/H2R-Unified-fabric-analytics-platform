"""Build a local CSV training dataset for the Phase 2 attrition workflow.

Run from ai-service:
    python scripts/build_attrition_features.py --horizon-days 90
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(AI_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_ROOT))

from app.config import Settings
from app.data.csv_gold import infer_as_of_from_value, load_gold
from app.data.feature_engineering import build_attrition_dataset, summarize_attrition_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Build leakage-aware attrition features.")
    parser.add_argument("--sample-data-dir", type=Path, default=None)
    parser.add_argument("--as-of", default=None, help="Optional source cutoff date (YYYY-MM-DD).")
    parser.add_argument("--horizon-days", type=int, default=90)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/attrition_training_dataset.csv"),
        help="Output CSV path; relative paths use the current directory.",
    )
    args = parser.parse_args()

    sample_data_dir = args.sample_data_dir or Settings().resolved_sample_data_dir()
    as_of = infer_as_of_from_value(args.as_of, sample_data_dir)
    gold = load_gold(sample_data_dir, as_of=as_of)
    if gold.employee_history is None:
        print("Employee history source missing. Run: python scripts/generate_synthetic_employee_history.py")
        return 2
    dataset = build_attrition_dataset(gold, horizon_days=args.horizon_days)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(args.output, index=False)
    summary = summarize_attrition_dataset(dataset)

    print(f"Source cutoff: {as_of.isoformat()}")
    print(f"Label horizon: {args.horizon_days} days")
    print(f"Output: {args.output.resolve()}")
    print(f"Eligible rows: {summary['row_count']}")
    print(f"Positive labels: {summary['positive_rows']}")
    print(f"Negative labels: {summary['negative_rows']}")
    if not summary["row_count"]:
        print("No mature employee-month examples are available for this horizon.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
