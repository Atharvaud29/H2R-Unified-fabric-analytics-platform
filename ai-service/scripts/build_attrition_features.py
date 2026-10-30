"""Build a leakage-aware attrition dataset from demo or governed HRIS history.

Run from ai-service:
    python scripts/build_attrition_features.py --horizon-days 90
    python scripts/build_attrition_features.py --hris-history-path /secure/hris/history.csv --output /secure/output/attrition.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AI_SERVICE_ROOT.parent
if str(AI_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_ROOT))

from app.config import Settings
from app.data.csv_gold import infer_as_of_from_value, load_gold
from app.data.feature_engineering import build_attrition_dataset, summarize_attrition_dataset
from app.data.hris_history_source import HrisHistorySourceError, load_governed_hris_history


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Build leakage-aware attrition features.")
    parser.add_argument("--sample-data-dir", type=Path, default=None)
    parser.add_argument("--as-of", default=None, help="Optional source cutoff date (YYYY-MM-DD).")
    parser.add_argument("--horizon-days", type=int, default=90)
    parser.add_argument(
        "--hris-history-path",
        type=Path,
        default=None,
        help="Approved governed HRIS history CSV. If omitted, the local synthetic demo history is used.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/attrition_training_dataset.csv"),
        help="Output CSV path; production runs must use a protected absolute path outside the repository.",
    )
    args = parser.parse_args()

    if args.hris_history_path is not None:
        if args.sample_data_dir is None or not args.sample_data_dir.is_absolute():
            print("Governed HRIS mode requires --sample-data-dir as an absolute path to approved protected Gold-equivalent CSV exports.")
            return 2
        if _is_within(args.sample_data_dir, REPO_ROOT):
            print("Governed HRIS mode cannot use repository/sample-data Gold inputs; supply approved protected Gold-equivalent exports.")
            return 2

    sample_data_dir = args.sample_data_dir or Settings().resolved_sample_data_dir()
    as_of = infer_as_of_from_value(args.as_of, sample_data_dir)
    gold = load_gold(sample_data_dir, as_of=as_of)

    if args.hris_history_path is not None:
        try:
            history, source_report = load_governed_hris_history(args.hris_history_path)
        except HrisHistorySourceError as exc:
            print(f"HRIS source validation failed: {exc}")
            return 2
        if not args.output.is_absolute() or _is_within(args.output, REPO_ROOT):
            print("Production output must be an absolute path outside the repository, on an approved protected storage location.")
            return 2
        gold.employee_history = history
        print("History source: governed HRIS production extract")
        print(f"Source system: {source_report['source_system']}")
        print(f"Validated source records: {source_report['source_record_count']}")
    elif gold.employee_history is None:
        print("Employee history source missing. Run: python scripts/generate_synthetic_employee_history.py")
        return 2
    else:
        print("History source: synthetic demo (not production training data)")

    dataset = build_attrition_dataset(gold, horizon_days=args.horizon_days)
    if args.hris_history_path is not None and dataset.empty:
        print("No mature employee-month examples are available for this horizon.")
        return 2

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
