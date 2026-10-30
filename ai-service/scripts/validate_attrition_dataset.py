"""Run aggregate-only quality checks on the repository's attrition feature data.

Run from ai-service:
    python scripts/validate_attrition_dataset.py --horizon-days 90

No employee-level rows or identifiers are printed or written by this validator.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(AI_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_ROOT))

from app.config import Settings
from app.data.csv_gold import infer_as_of_from_value, load_gold
from app.data.feature_engineering import (
    DATASET_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    ROW_METADATA_COLUMNS,
    TARGET_COLUMN,
    build_attrition_dataset,
)

FORBIDDEN_MODEL_FIELDS = {
    "gender", "date_of_birth", "age", "email", "first_name", "last_name",
    "full_name", "manager_id", "termination_date", "last_working_date",
    "exit_type", "exit_reason", "regrettable_flag",
}


def validate_dataset(dataset: pd.DataFrame, as_of, horizon_days: int) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    actual_columns = list(dataset.columns)
    if actual_columns != list(DATASET_COLUMNS):
        errors.append("Dataset columns do not match the declared Phase 2 schema.")

    missing_model_columns = sorted(set(MODEL_FEATURE_COLUMNS).difference(dataset.columns))
    if missing_model_columns:
        errors.append("Required model feature columns are missing.")

    forbidden_present = sorted(FORBIDDEN_MODEL_FIELDS.intersection(dataset.columns))
    if forbidden_present:
        errors.append("One or more prohibited fields are present in the dataset.")

    row_count = int(len(dataset))
    if row_count == 0:
        errors.append("No eligible employee-month examples were generated.")

    duplicate_keys = 0
    if {"employee_id", "snapshot_date"}.issubset(dataset.columns):
        duplicate_keys = int(dataset.duplicated(["employee_id", "snapshot_date"]).sum())
        if duplicate_keys:
            errors.append("Duplicate employee-month keys were detected.")

    null_counts = {
        column: int(dataset[column].isna().sum())
        for column in MODEL_FEATURE_COLUMNS
        if column in dataset.columns
    }
    if any(null_counts.values()):
        errors.append("Null values remain in one or more model features.")

    unknown_counts = {
        column: int(dataset[column].astype(str).str.strip().eq("Unknown").sum())
        for column in ("department_id", "location_id", "grade_id", "employment_type", "work_mode")
        if column in dataset.columns
    }
    if any(unknown_counts.values()):
        warnings.append("Some categorical features contain the Unknown placeholder.")

    target_values = sorted(dataset[TARGET_COLUMN].dropna().astype(int).unique().tolist()) if TARGET_COLUMN in dataset else []
    if TARGET_COLUMN not in dataset or not set(target_values).issubset({0, 1}):
        errors.append("Target must contain only binary values 0 and 1.")

    positives = int(dataset[TARGET_COLUMN].fillna(0).astype(int).sum()) if TARGET_COLUMN in dataset else 0
    negatives = row_count - positives
    class_diversity = positives > 0 and negatives > 0
    if row_count and not class_diversity:
        warnings.append("Only one target class is present; supervised binary model training is not ready.")

    snapshot_dates = pd.to_datetime(dataset["snapshot_date"], errors="coerce") if "snapshot_date" in dataset else pd.Series(dtype="datetime64[ns]")
    invalid_snapshots = int(snapshot_dates.isna().sum())
    future_snapshots = int((snapshot_dates.dt.date > as_of).sum()) if row_count else 0
    if invalid_snapshots or future_snapshots:
        errors.append("Invalid or future snapshot dates were detected.")

    report = {
        "status": "pass" if not errors else "fail",
        "as_of": as_of.isoformat(),
        "horizon_days": int(horizon_days),
        "row_count": row_count,
        "distinct_employee_count": int(dataset["employee_id"].nunique()) if "employee_id" in dataset else 0,
        "distinct_snapshot_count": int(dataset["snapshot_date"].nunique()) if "snapshot_date" in dataset else 0,
        "snapshot_min": str(snapshot_dates.min().date()) if row_count and snapshot_dates.notna().any() else None,
        "snapshot_max": str(snapshot_dates.max().date()) if row_count and snapshot_dates.notna().any() else None,
        "positive_rows": positives,
        "negative_rows": negatives,
        "positive_rate": (positives / row_count) if row_count else None,
        "class_diversity_pass": class_diversity,
        "duplicate_employee_month_keys": duplicate_keys,
        "null_feature_counts": null_counts,
        "unknown_category_counts": unknown_counts,
        "metadata_columns": list(ROW_METADATA_COLUMNS),
        "model_feature_columns": list(MODEL_FEATURE_COLUMNS),
        "forbidden_model_fields_present": forbidden_present,
        "errors": errors,
        "warnings": warnings,
        "historical_feature_warning": (
            "Employee attributes are sourced from the current employee record, not an "
            "effective-dated history. Historical department/location/grade/employment "
            "features are therefore not point-in-time validated."
        ),
        "training_readiness": (
            "not_ready" if errors or not class_diversity or any(unknown_counts.values())
            else "technical_checks_pass_historical_review_required"
        ),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Phase 2 attrition dataset.")
    parser.add_argument("--sample-data-dir", type=Path, default=None)
    parser.add_argument("--as-of", default=None, help="Optional source cutoff date (YYYY-MM-DD).")
    parser.add_argument("--horizon-days", type=int, default=90)
    parser.add_argument("--report-json", type=Path, default=None, help="Optional aggregate-only JSON report path.")
    args = parser.parse_args()

    sample_data_dir = args.sample_data_dir or Settings().resolved_sample_data_dir()
    as_of = infer_as_of_from_value(args.as_of, sample_data_dir)
    gold = load_gold(sample_data_dir, as_of=as_of)
    dataset = build_attrition_dataset(gold, horizon_days=args.horizon_days)
    report = validate_dataset(dataset, as_of, args.horizon_days)

    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(rendered + "\n", encoding="utf-8")

    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
