from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data.hris_history_source import HrisHistorySourceError, load_governed_hris_history


COLUMNS = [
    "employee_id", "effective_start_date", "effective_end_date", "recorded_at",
    "superseded_at", "department_id", "location_id", "grade_id",
    "employment_type", "work_mode", "source_system", "source_record_id",
    "extracted_at", "source_type",
]


def _row(**updates):
    row = {
        "employee_id": "E001", "effective_start_date": "2023-01-01",
        "effective_end_date": "", "recorded_at": "2023-01-01T08:00:00Z",
        "superseded_at": "", "department_id": "D01", "location_id": "L01",
        "grade_id": "G2", "employment_type": "Full-Time", "work_mode": "Hybrid",
        "source_system": "HRIS_A", "source_record_id": "rec-001",
        "extracted_at": "2026-10-01T00:00:00Z", "source_type": "hris_production",
    }
    row.update(updates)
    return row


def _write(tmp_path, rows):
    path = tmp_path / "hris_history.csv"
    pd.DataFrame(rows, columns=COLUMNS).to_csv(path, index=False)
    return path


def test_loads_canonical_governed_history_and_returns_aggregate_report(tmp_path):
    history, report = load_governed_hris_history(_write(tmp_path, [_row()]))
    assert report["status"] == "pass"
    assert report["source_type"] == "hris_production"
    assert report["source_system"] == "HRIS_A"
    assert report["source_record_count"] == 1
    assert history.iloc[0]["department_id"] == "D01"


def test_rejects_synthetic_demo_history(tmp_path):
    path = _write(tmp_path, [_row(source_type="synthetic_demo")])
    with pytest.raises(HrisHistorySourceError, match="Only explicitly approved"):
        load_governed_hris_history(path)


def test_rejects_missing_lineage_columns(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame([{"employee_id": "E001"}]).to_csv(path, index=False)
    with pytest.raises(HrisHistorySourceError, match="missing required contract columns"):
        load_governed_hris_history(path)


def test_rejects_duplicate_source_record_ids(tmp_path):
    rows = [_row(), _row(employee_id="E002")]
    path = _write(tmp_path, rows)
    with pytest.raises(HrisHistorySourceError, match="source_record_id must be unique"):
        load_governed_hris_history(path)


def test_rejects_multiple_source_systems_or_extract_timestamps(tmp_path):
    path = _write(tmp_path, [_row(), _row(employee_id="E002", source_record_id="rec-002", source_system="HRIS_B")])
    with pytest.raises(HrisHistorySourceError, match="exactly one source_system"):
        load_governed_hris_history(path)


def test_rejects_overlapping_bitemporal_versions(tmp_path):
    rows = [
        _row(source_record_id="rec-001", effective_end_date="2024-01-01"),
        _row(source_record_id="rec-002", effective_start_date="2023-06-01"),
    ]
    path = _write(tmp_path, rows)
    with pytest.raises(HrisHistorySourceError, match="bitemporal history validation failed"):
        load_governed_hris_history(path)
