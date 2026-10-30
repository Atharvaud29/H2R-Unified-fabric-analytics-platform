"""Leakage-aware workforce attrition feature dataset preparation."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from app.data.csv_gold import GoldTables
from app.data.employee_history import EmployeeHistoryError, point_in_time_employee_attributes

# Identifiers are metadata only. Sensitive/protected attributes and direct
# identifiers are deliberately excluded from the model input contract.
MODEL_FEATURE_COLUMNS = (
    "department_id", "location_id", "grade_id", "employment_type", "work_mode",
    "tenure_months", "hire_month", "snapshot_month", "snapshot_quarter",
)
ROW_METADATA_COLUMNS = ("employee_id", "snapshot_date")
TARGET_COLUMN = "exit_within_horizon"
DATASET_COLUMNS = (*ROW_METADATA_COLUMNS, *MODEL_FEATURE_COLUMNS, TARGET_COLUMN)


class FeatureEngineeringError(ValueError):
    """Raised when Gold-equivalent inputs cannot support feature generation."""


def _as_date_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce").dt.date


def _categorical_value(value: Any) -> str:
    if pd.isna(value) or str(value).strip() == "":
        return "Unknown"
    return str(value).strip()


def _completed_months(hire_date: date, snapshot_date: date) -> int:
    months = (snapshot_date.year - hire_date.year) * 12
    months += snapshot_date.month - hire_date.month
    if snapshot_date.day < hire_date.day:
        months -= 1
    return max(months, 0)


def build_attrition_dataset(gold: GoldTables, horizon_days: int = 90) -> pd.DataFrame:
    """Build active employee-month examples with a fully observed forward label.

    The target is 1 when a last-working-date event occurs in
    (snapshot_date, snapshot_date + horizon_days]. Recent snapshots whose
    complete horizon is not observable by gold.as_of are censored and omitted.
    Future termination fields are never used as model inputs.
    """
    if isinstance(horizon_days, bool) or not isinstance(horizon_days, int) or horizon_days <= 0:
        raise FeatureEngineeringError("horizon_days must be a positive integer.")

    required = {
        "headcount_monthly": (gold.headcount_monthly, {"month_end", "employee_id", "is_month_end_active"}),
        "employees": (gold.employees, {"employee_id", "hire_date"}),
        "exits": (gold.exits, {"employee_id", "last_working_date"}),
    }
    for name, (frame, columns) in required.items():
        missing = columns.difference(frame.columns)
        if missing:
            raise FeatureEngineeringError(
                f"{name} is missing required columns: " + ", ".join(sorted(missing))
            )

    if gold.headcount_monthly.empty or gold.employees.empty:
        return pd.DataFrame(columns=DATASET_COLUMNS)

    hc = gold.headcount_monthly.copy()
    hc["_snapshot_date"] = _as_date_series(hc["month_end"])
    hc = hc.loc[
        hc["_snapshot_date"].notna()
        & hc["is_month_end_active"].fillna(False).astype(bool)
        & (hc["_snapshot_date"] <= gold.as_of)
    ].copy()
    if hc.empty:
        return pd.DataFrame(columns=DATASET_COLUMNS)

    snapshots = sorted(
        snapshot for snapshot in hc["_snapshot_date"].unique().tolist()
        if snapshot + timedelta(days=horizon_days) <= gold.as_of
    )
    if not snapshots:
        return pd.DataFrame(columns=DATASET_COLUMNS)
    if gold.employee_history is None:
        raise FeatureEngineeringError(
            "Employee history source is required. Generate sample-data/hris_employee_history_synthetic.csv "
            "with scripts/generate_synthetic_employee_history.py; current-state fallback is disabled."
        )

    employees = gold.employees.copy()
    employees["employee_id"] = employees["employee_id"].astype(str).str.strip()
    employees = employees.drop_duplicates("employee_id", keep="first")
    employee_lookup = employees.set_index("employee_id", drop=False)

    exits = gold.exits.copy()
    exits["employee_id"] = exits["employee_id"].astype(str).str.strip()
    exits["_exit_date"] = _as_date_series(exits["last_working_date"])
    exits = exits.loc[exits["_exit_date"].notna()].copy()

    rows: list[dict[str, Any]] = []
    for snapshot in snapshots:
        horizon_end = snapshot + timedelta(days=horizon_days)
        active_ids = (
            hc.loc[hc["_snapshot_date"] == snapshot, "employee_id"]
            .astype(str).str.strip().drop_duplicates().tolist()
        )
        active_ids = [key for key in active_ids if key in employee_lookup.index]
        if not active_ids:
            continue

        snapshot_keys = pd.DataFrame({"employee_id": active_ids, "snapshot_date": snapshot.isoformat()})
        try:
            historical_attributes = point_in_time_employee_attributes(snapshot_keys, gold.employee_history)
        except EmployeeHistoryError as exc:
            raise FeatureEngineeringError("Point-in-time employee history resolution failed: " + str(exc)) from exc
        attribute_lookup = historical_attributes.set_index("employee_id").to_dict("index")

        future_exits = exits.loc[
            (exits["_exit_date"] > snapshot) & (exits["_exit_date"] <= horizon_end),
            "employee_id",
        ]
        exited_ids = set(future_exits.tolist())

        for employee_id in active_ids:
            employee = employee_lookup.loc[employee_id]
            if isinstance(employee, pd.DataFrame):
                employee = employee.iloc[0]
            hire_date = pd.to_datetime(employee.get("hire_date"), errors="coerce")
            if pd.isna(hire_date) or hire_date.date() > snapshot:
                continue

            rows.append({
                "employee_id": employee_id,
                "snapshot_date": snapshot.isoformat(),
                "department_id": _categorical_value(attribute_lookup[employee_id]["department_id"]),
                "location_id": _categorical_value(attribute_lookup[employee_id]["location_id"]),
                "grade_id": _categorical_value(attribute_lookup[employee_id]["grade_id"]),
                "employment_type": _categorical_value(attribute_lookup[employee_id]["employment_type"]),
                "work_mode": _categorical_value(attribute_lookup[employee_id]["work_mode"]),
                "tenure_months": _completed_months(hire_date.date(), snapshot),
                "hire_month": int(hire_date.month),
                "snapshot_month": int(snapshot.month),
                "snapshot_quarter": int(((snapshot.month - 1) // 3) + 1),
                TARGET_COLUMN: int(employee_id in exited_ids),
            })

    dataset = pd.DataFrame(rows, columns=DATASET_COLUMNS)
    if not dataset.empty:
        dataset[TARGET_COLUMN] = dataset[TARGET_COLUMN].astype("int8")
        dataset["tenure_months"] = dataset["tenure_months"].astype("int32")
    return dataset


def summarize_attrition_dataset(dataset: pd.DataFrame) -> dict[str, Any]:
    """Return aggregate-only diagnostics; never return employee-level values."""
    if TARGET_COLUMN not in dataset.columns:
        raise FeatureEngineeringError(f"Dataset must include target column {TARGET_COLUMN}.")
    row_count = int(len(dataset))
    positives = int(dataset[TARGET_COLUMN].fillna(0).astype(int).sum()) if row_count else 0
    negatives = row_count - positives
    return {
        "row_count": row_count,
        "positive_rows": positives,
        "negative_rows": negatives,
        "positive_rate": (positives / row_count) if row_count else None,
        "model_features": list(MODEL_FEATURE_COLUMNS),
        "metadata_columns": list(ROW_METADATA_COLUMNS),
        "target": TARGET_COLUMN,
    }
