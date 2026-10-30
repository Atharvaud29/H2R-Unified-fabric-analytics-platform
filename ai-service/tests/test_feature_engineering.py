from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data.csv_gold import GoldTables
from app.data.feature_engineering import (
    DATASET_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    TARGET_COLUMN,
    FeatureEngineeringError,
    build_attrition_dataset,
    summarize_attrition_dataset,
)


def _gold() -> GoldTables:
    employees = pd.DataFrame([
        {
            "employee_id": "E001", "hire_date": date(2023, 1, 15),
            "department_id": "D01", "location_id": "L01", "grade_id": "G2",
            "employment_type": "Full-Time", "work_mode": "Hybrid",
            "gender": "Female", "date_of_birth": date(1990, 1, 1),
            "email": "private@example.test", "full_name": "Private Person",
            "manager_id": "M001", "termination_date": date(2024, 3, 15),
        },
        {
            "employee_id": "E002", "hire_date": date(2023, 6, 10),
            "department_id": "D02", "location_id": "L02", "grade_id": "G3",
            "employment_type": "Contract", "work_mode": "Remote",
            "gender": "Male", "date_of_birth": date(1988, 6, 1),
            "email": "private2@example.test", "full_name": "Private Person Two",
            "manager_id": "M002", "termination_date": None,
        },
    ])
    headcount = pd.DataFrame([
        {"month_end": date(2024, 1, 31), "employee_id": "E001", "is_month_end_active": True},
        {"month_end": date(2024, 1, 31), "employee_id": "E002", "is_month_end_active": True},
        {"month_end": date(2024, 4, 30), "employee_id": "E002", "is_month_end_active": True},
        {"month_end": date(2025, 1, 31), "employee_id": "E002", "is_month_end_active": True},
    ])
    exits = pd.DataFrame([
        {"employee_id": "E001", "last_working_date": date(2024, 3, 15)},
        {"employee_id": "E002", "last_working_date": date(2024, 5, 1)},
    ])
    return GoldTables(
        as_of=date(2024, 12, 31),
        employees=employees,
        quarantined_employee_count=0,
        headcount_monthly=headcount,
        recruitment=pd.DataFrame(),
        exits=exits,
    )


def test_builds_forward_exit_label_and_snapshot_tenure():
    dataset = build_attrition_dataset(_gold(), horizon_days=90)
    jan_rows = dataset.loc[dataset["snapshot_date"] == "2024-01-31"].set_index("employee_id")

    assert jan_rows.loc["E001", TARGET_COLUMN] == 1
    assert jan_rows.loc["E002", TARGET_COLUMN] == 0
    assert jan_rows.loc["E001", "tenure_months"] == 12


def test_only_active_snapshots_and_fully_observed_horizons_are_included():
    dataset = build_attrition_dataset(_gold(), horizon_days=90)

    assert set(dataset["snapshot_date"]) == {"2024-01-31", "2024-04-30"}
    assert not ((dataset["employee_id"] == "E001") & (dataset["snapshot_date"] == "2024-04-30")).any()
    assert not (dataset["snapshot_date"] == "2025-01-31").any()


def test_model_inputs_exclude_identifiers_and_sensitive_attributes():
    dataset = build_attrition_dataset(_gold(), horizon_days=90)

    assert tuple(MODEL_FEATURE_COLUMNS) == (
        "department_id", "location_id", "grade_id", "employment_type", "work_mode",
        "tenure_months", "hire_month", "snapshot_month", "snapshot_quarter",
    )
    assert list(dataset.columns) == list(DATASET_COLUMNS)
    forbidden = {
        "gender", "date_of_birth", "age", "email", "full_name",
        "manager_id", "termination_date",
    }
    assert forbidden.isdisjoint(dataset.columns)
    assert "employee_id" not in MODEL_FEATURE_COLUMNS


def test_exit_on_horizon_boundary_is_positive():
    gold = _gold()
    gold.exits = pd.DataFrame([
        {"employee_id": "E002", "last_working_date": date(2024, 4, 30)}
    ])
    dataset = build_attrition_dataset(gold, horizon_days=90)
    row = dataset.loc[
        (dataset["employee_id"] == "E002") & (dataset["snapshot_date"] == "2024-01-31")
    ]
    assert int(row.iloc[0][TARGET_COLUMN]) == 1


def test_rejects_invalid_horizon():
    with pytest.raises(FeatureEngineeringError, match="positive integer"):
        build_attrition_dataset(_gold(), horizon_days=0)


def test_summary_contains_aggregate_counts_only():
    dataset = build_attrition_dataset(_gold(), horizon_days=90)
    summary = summarize_attrition_dataset(dataset)

    assert summary["row_count"] == len(dataset)
    assert summary["positive_rows"] == int(dataset[TARGET_COLUMN].sum())
    assert summary["positive_rows"] + summary["negative_rows"] == summary["row_count"]
    assert "employee_id" not in summary
