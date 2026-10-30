"""Independent validation of point-in-time attrition feature datasets.

The validator reports aggregate diagnostics only. It never emits employee-level
records or identifiers.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Any

import pandas as pd

from app.data.csv_gold import GoldTables
from app.data.employee_history import (
    ATTRIBUTE_COLUMNS,
    EmployeeHistoryError,
    point_in_time_employee_attributes,
    validate_employee_history,
)
from app.data.feature_engineering import (
    DATASET_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    ROW_METADATA_COLUMNS,
    TARGET_COLUMN,
)


def _dates(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce").dt.date


def _months_between(hire_date: date, snapshot_date: date) -> int:
    months = (snapshot_date.year - hire_date.year) * 12 + snapshot_date.month - hire_date.month
    if snapshot_date.day < hire_date.day:
        months -= 1
    return max(months, 0)


def validate_point_in_time_dataset(
    dataset: pd.DataFrame,
    gold: GoldTables,
    horizon_days: int = 90,
) -> dict[str, Any]:
    """Recompute temporal expectations from Gold inputs and compare aggregate counts."""
    errors: list[str] = []
    warnings: list[str] = []
    if isinstance(horizon_days, bool) or not isinstance(horizon_days, int) or horizon_days <= 0:
        return {
            "status": "fail", "errors": ["horizon_days must be a positive integer."],
            "warnings": [], "row_count": int(len(dataset)),
        }

    if list(dataset.columns) != list(DATASET_COLUMNS):
        errors.append("Dataset columns do not match the declared feature contract.")
    missing = sorted(set(DATASET_COLUMNS).difference(dataset.columns))
    if missing:
        return {
            "status": "fail", "errors": errors + ["Required dataset columns are missing."],
            "warnings": warnings, "row_count": int(len(dataset)),
        }

    row_count = int(len(dataset))
    if row_count == 0:
        errors.append("No eligible employee-month examples were generated.")

    duplicate_keys = int(dataset.duplicated(list(ROW_METADATA_COLUMNS)).sum())
    if duplicate_keys:
        errors.append("Duplicate employee-month keys were detected.")

    null_feature_count = int(dataset.loc[:, MODEL_FEATURE_COLUMNS].isna().sum().sum())
    if null_feature_count:
        errors.append("Null values remain in model features.")

    target = pd.to_numeric(dataset[TARGET_COLUMN], errors="coerce")
    invalid_target_count = int((target.isna() | ~target.isin([0, 1])).sum())
    if invalid_target_count:
        errors.append("Target contains null or non-binary values.")

    snapshot_dates = _dates(dataset["snapshot_date"])
    invalid_snapshot_count = int(snapshot_dates.isna().sum())
    invalid_horizon_count = int(sum(
        value is not None and value + timedelta(days=horizon_days) > gold.as_of
        for value in snapshot_dates
    ))
    if invalid_snapshot_count or invalid_horizon_count:
        errors.append("Invalid snapshots or incomplete forward-label horizons were detected.")

    non_month_end_count = 0
    for value in snapshot_dates.dropna():
        if value.day != monthrange(value.year, value.month)[1]:
            non_month_end_count += 1
    if non_month_end_count:
        errors.append("Snapshot dates must be month-end dates.")

    history = gold.employee_history
    history_report: dict[str, Any] = {"status": "fail", "history_rows": 0}
    history_source_type = "missing"
    if history is None:
        errors.append("Historical employee source is missing; current-state fallback is prohibited.")
    else:
        if "source_type" in history.columns:
            source_types = sorted(history["source_type"].dropna().astype(str).unique().tolist())
            history_source_type = source_types[0] if len(source_types) == 1 else "mixed_or_unknown"
            if len(source_types) != 1:
                errors.append("History source provenance is missing or inconsistent.")
        else:
            history_source_type = "unlabelled"
            errors.append("History source provenance marker is missing.")
        try:
            history_report = validate_employee_history(history)
            if history_report["status"] != "pass":
                errors.append("Bitemporal history contains overlapping versions.")
        except EmployeeHistoryError:
            errors.append("Bitemporal history schema or interval validation failed.")

    # Compare the persisted feature values with a fresh bitemporal lookup.
    history_mismatch_count = 0
    if history is not None and invalid_snapshot_count == 0 and row_count:
        keys = dataset.loc[:, ["employee_id", "snapshot_date"]].copy()
        try:
            expected_history = point_in_time_employee_attributes(keys, history)
            actual = dataset.loc[:, ["employee_id", "snapshot_date", *ATTRIBUTE_COLUMNS]].copy()
            expected = expected_history
            merged = actual.merge(
                expected,
                on=["employee_id", "snapshot_date"],
                how="left",
                suffixes=("_actual", "_expected"),
                validate="one_to_one",
            )
            for column in ATTRIBUTE_COLUMNS:
                history_mismatch_count += int(
                    merged[f"{column}_actual"].astype("string").fillna("<NULL>")
                    .ne(merged[f"{column}_expected"].astype("string").fillna("<NULL>")).sum()
                )
        except (EmployeeHistoryError, KeyError, ValueError):
            history_mismatch_count = row_count * len(ATTRIBUTE_COLUMNS)
            errors.append("One or more dataset snapshots do not resolve to exactly one bitemporal history version.")
    if history_mismatch_count:
        errors.append("Historical feature values do not match the point-in-time source.")

    # Independently recompute labels and immutable hire-date-derived features.
    employee_lookup = gold.employees.copy()
    if "employee_id" in employee_lookup.columns:
        employee_lookup["employee_id"] = employee_lookup["employee_id"].astype(str).str.strip()
        employee_lookup = employee_lookup.drop_duplicates("employee_id").set_index("employee_id")
    exit_mismatch_count = 0
    tenure_mismatch_count = 0
    calendar_mismatch_count = 0
    missing_employee_count = 0
    exits = gold.exits.copy()
    if {"employee_id", "last_working_date"}.issubset(exits.columns):
        exits["employee_id"] = exits["employee_id"].astype(str).str.strip()
        exits["_exit_date"] = _dates(exits["last_working_date"])
    else:
        exits = pd.DataFrame(columns=["employee_id", "_exit_date"])
        errors.append("Exit events lack employee_id or last_working_date.")

    active_keys: set[tuple[str, date]] = set()
    if {"employee_id", "month_end", "is_month_end_active"}.issubset(gold.headcount_monthly.columns):
        for row in gold.headcount_monthly.loc[
            gold.headcount_monthly["is_month_end_active"].fillna(False).astype(bool)
        ].itertuples(index=False):
            parsed = pd.to_datetime(row.month_end, errors="coerce")
            if not pd.isna(parsed):
                active_keys.add((str(row.employee_id).strip(), parsed.date()))
    else:
        errors.append("Gold headcount table lacks active employee-month keys.")

    for row in dataset.itertuples(index=False):
        employee_id = str(row.employee_id).strip()
        snapshot = pd.to_datetime(row.snapshot_date, errors="coerce")
        if pd.isna(snapshot):
            continue
        snapshot_date = snapshot.date()
        if (employee_id, snapshot_date) not in active_keys:
            errors.append("Dataset contains a row that is not an active Gold employee-month snapshot.")
            # Keep processing to report the other aggregate diagnostics.
        if employee_id not in employee_lookup.index:
            missing_employee_count += 1
            continue
        employee = employee_lookup.loc[employee_id]
        hire = pd.to_datetime(employee.get("hire_date"), errors="coerce")
        if pd.isna(hire) or hire.date() > snapshot_date:
            tenure_mismatch_count += 1
        else:
            expected_tenure = _months_between(hire.date(), snapshot_date)
            if int(row.tenure_months) != expected_tenure or int(row.hire_month) != hire.month:
                tenure_mismatch_count += 1
        expected_quarter = ((snapshot_date.month - 1) // 3) + 1
        if int(row.snapshot_month) != snapshot_date.month or int(row.snapshot_quarter) != expected_quarter:
            calendar_mismatch_count += 1
        horizon_end = snapshot_date + timedelta(days=horizon_days)
        employee_exits = exits.loc[
            (exits["employee_id"] == employee_id)
            & (exits["_exit_date"] > snapshot_date)
            & (exits["_exit_date"] <= horizon_end)
        ]
        expected_label = int(not employee_exits.empty)
        try:
            actual_label = int(row.exit_within_horizon)
        except (TypeError, ValueError):
            actual_label = -1
        if actual_label != expected_label:
            exit_mismatch_count += 1

    if missing_employee_count:
        errors.append("Dataset references employees absent from the Gold employee dimension.")
    if tenure_mismatch_count:
        errors.append("Tenure or hire-month features do not match the employee hire date.")
    if calendar_mismatch_count:
        errors.append("Snapshot month or quarter features are inconsistent with snapshot_date.")
    if exit_mismatch_count:
        errors.append("Attrition labels do not match independently recomputed forward exit events.")

    positives = int(target.fillna(0).sum())
    negatives = row_count - positives
    class_diversity = positives > 0 and negatives > 0
    if row_count and not class_diversity:
        warnings.append("Only one target class is present; supervised binary model training is not ready.")
    if history_source_type == "synthetic_demo":
        warnings.append("Synthetic demonstration history validates mechanics only; it is not observed HRIS history.")

    return {
        "status": "pass" if not errors else "fail",
        "as_of": gold.as_of.isoformat(),
        "horizon_days": horizon_days,
        "row_count": row_count,
        "positive_rows": positives,
        "negative_rows": negatives,
        "positive_rate": positives / row_count if row_count else None,
        "distinct_employee_count": int(dataset["employee_id"].nunique()),
        "distinct_snapshot_count": int(dataset["snapshot_date"].nunique()),
        "duplicate_employee_month_keys": duplicate_keys,
        "null_model_feature_values": null_feature_count,
        "invalid_target_rows": invalid_target_count,
        "invalid_snapshot_rows": invalid_snapshot_count,
        "incomplete_horizon_rows": invalid_horizon_count,
        "non_month_end_snapshots": non_month_end_count,
        "bitemporal_history_status": history_report.get("status"),
        "bitemporal_history_rows": int(history_report.get("history_rows", 0)),
        "history_source_type": history_source_type,
        "history_feature_value_mismatches": history_mismatch_count,
        "tenure_feature_mismatches": tenure_mismatch_count,
        "calendar_feature_mismatches": calendar_mismatch_count,
        "forward_exit_label_mismatches": exit_mismatch_count,
        "missing_employee_references": missing_employee_count,
        "model_feature_columns": list(MODEL_FEATURE_COLUMNS),
        "metadata_columns": list(ROW_METADATA_COLUMNS),
        "target_column": TARGET_COLUMN,
        "class_diversity_pass": class_diversity,
        "training_readiness": (
            "not_ready" if errors or not class_diversity
            else "synthetic_demo_only_not_production_ready" if history_source_type == "synthetic_demo"
            else "technical_checks_pass_source_governance_review_required"
        ),
        "errors": sorted(set(errors)),
        "warnings": warnings,
    }
