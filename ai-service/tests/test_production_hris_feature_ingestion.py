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
from app.data.hris_history_source import load_governed_hris_history


def test_governed_history_flows_into_point_in_time_feature_builder(tmp_path):
    source = tmp_path / "approved_history.csv"
    pd.DataFrame([{
        "employee_id": "PSEUDO-001",
        "effective_start_date": "2023-01-01",
        "effective_end_date": "",
        "recorded_at": "2023-01-01T00:00:00Z",
        "superseded_at": "",
        "department_id": "DEPT-A",
        "location_id": "LOC-A",
        "grade_id": "G4",
        "employment_type": "Full-Time",
        "work_mode": "Hybrid",
        "source_system": "APPROVED_HRIS",
        "source_record_id": "immutable-version-001",
        "extracted_at": "2026-10-01T00:00:00Z",
        "source_type": "hris_production",
    }]).to_csv(source, index=False)

    history, report = load_governed_hris_history(source)
    gold = GoldTables(
        as_of=date(2024, 12, 31),
        employees=pd.DataFrame([{
            "employee_id": "PSEUDO-001",
            "hire_date": date(2023, 1, 1),
        }]),
        quarantined_employee_count=0,
        headcount_monthly=pd.DataFrame([{
            "month_end": date(2024, 1, 31),
            "employee_id": "PSEUDO-001",
            "is_month_end_active": True,
        }]),
        recruitment=pd.DataFrame(),
        exits=pd.DataFrame(columns=["employee_id", "last_working_date"]),
        employee_history=history,
    )

    dataset = build_attrition_dataset(gold, horizon_days=90)

    assert report["status"] == "pass"
    assert len(dataset) == 1
    assert dataset.iloc[0]["department_id"] == "DEPT-A"
    assert dataset.iloc[0]["location_id"] == "LOC-A"
    assert dataset.iloc[0]["exit_within_horizon"] == 0
    assert "PSEUDO-001" not in dataset.drop(columns=["employee_id"]).to_string()


def test_governed_extract_requires_one_timezone_aware_extraction_timestamp(tmp_path):
    source = tmp_path / "mixed_extract_times.csv"
    row = {
        "employee_id": "PSEUDO-001",
        "effective_start_date": "2023-01-01",
        "effective_end_date": "",
        "recorded_at": "2023-01-01T00:00:00Z",
        "superseded_at": "",
        "department_id": "DEPT-A",
        "location_id": "LOC-A",
        "grade_id": "G4",
        "employment_type": "Full-Time",
        "work_mode": "Hybrid",
        "source_system": "APPROVED_HRIS",
        "source_record_id": "immutable-version-001",
        "extracted_at": "2026-10-01T00:00:00Z",
        "source_type": "hris_production",
    }
    second = {**row, "employee_id": "PSEUDO-002", "source_record_id": "immutable-version-002",
              "extracted_at": "2026-10-02T00:00:00Z"}
    pd.DataFrame([row, second]).to_csv(source, index=False)

    try:
        load_governed_hris_history(source)
    except ValueError as exc:
        assert "share the same extracted_at" in str(exc)
    else:
        raise AssertionError("Mixed extraction timestamps should be rejected.")
