from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data.csv_gold import GoldTables
from app.data.feature_engineering import build_attrition_dataset
from app.data.point_in_time_validation import validate_point_in_time_dataset


def _gold() -> GoldTables:
    employees = pd.DataFrame([
        {"employee_id": "E001", "hire_date": date(2023, 1, 15)},
        {"employee_id": "E002", "hire_date": date(2023, 6, 10)},
    ])
    headcount = pd.DataFrame([
        {"month_end": date(2024, 1, 31), "employee_id": "E001", "is_month_end_active": True},
        {"month_end": date(2024, 1, 31), "employee_id": "E002", "is_month_end_active": True},
    ])
    history = pd.DataFrame([
        {"employee_id": "E001", "effective_start_date": "2023-01-15", "effective_end_date": None, "recorded_at": "2023-01-15T00:00:00Z", "superseded_at": None, "department_id": "D01", "location_id": "L01", "grade_id": "G2", "employment_type": "Full-Time", "work_mode": "Hybrid", "source_type": "synthetic_demo"},
        {"employee_id": "E002", "effective_start_date": "2023-06-10", "effective_end_date": None, "recorded_at": "2023-06-10T00:00:00Z", "superseded_at": None, "department_id": "D02", "location_id": "L02", "grade_id": "G3", "employment_type": "Contract", "work_mode": "Remote", "source_type": "synthetic_demo"},
    ])
    exits = pd.DataFrame([
        {"employee_id": "E001", "last_working_date": date(2024, 3, 15)},
    ])
    return GoldTables(
        as_of=date(2024, 12, 31),
        employees=employees,
        quarantined_employee_count=0,
        headcount_monthly=headcount,
        recruitment=pd.DataFrame(),
        exits=exits,
        employee_history=history,
    )


def test_validates_point_in_time_features_labels_and_snapshot_contract():
    gold = _gold()
    dataset = build_attrition_dataset(gold, horizon_days=90)
    report = validate_point_in_time_dataset(dataset, gold, horizon_days=90)

    assert report["status"] == "pass"
    assert report["history_feature_value_mismatches"] == 0
    assert report["forward_exit_label_mismatches"] == 0
    assert report["training_readiness"] == "synthetic_demo_only_not_production_ready"


def test_detects_historical_feature_tampering():
    gold = _gold()
    dataset = build_attrition_dataset(gold, horizon_days=90)
    dataset.loc[dataset["employee_id"] == "E001", "department_id"] = "D99"

    report = validate_point_in_time_dataset(dataset, gold, horizon_days=90)

    assert report["status"] == "fail"
    assert report["history_feature_value_mismatches"] > 0


def test_detects_forward_label_tampering():
    gold = _gold()
    dataset = build_attrition_dataset(gold, horizon_days=90)
    dataset.loc[dataset["employee_id"] == "E001", "exit_within_horizon"] = 0

    report = validate_point_in_time_dataset(dataset, gold, horizon_days=90)

    assert report["status"] == "fail"
    assert report["forward_exit_label_mismatches"] == 1


def test_fails_closed_when_history_is_missing():
    gold = _gold()
    gold.employee_history = None
    dataset = build_attrition_dataset(gold, horizon_days=90)

    # Feature generation itself is expected to fail before a dataset can be validated.
    # A hand-built empty dataset still receives an explicit missing-source diagnostic.
    empty = pd.DataFrame(columns=[
        "employee_id", "snapshot_date", "department_id", "location_id", "grade_id",
        "employment_type", "work_mode", "tenure_months", "hire_month",
        "snapshot_month", "snapshot_quarter", "exit_within_horizon",
    ])
    report = validate_point_in_time_dataset(empty, gold, horizon_days=90)
    assert report["status"] == "fail"
    assert any("Historical employee source is missing" in item for item in report["errors"])
