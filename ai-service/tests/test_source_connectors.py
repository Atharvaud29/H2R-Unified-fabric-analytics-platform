from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data.hris_history_source import HrisHistorySourceError
from app.data.source_connectors import (
    SourceReadContext,
    read_governed_history,
    validate_connector_result,
)


def _frame():
    return pd.DataFrame([{
        "employee_id": "E001",
        "effective_start_date": "2023-01-01",
        "effective_end_date": "",
        "recorded_at": "2023-01-01T08:00:00Z",
        "superseded_at": "",
        "department_id": "D01",
        "location_id": "L01",
        "grade_id": "G2",
        "employment_type": "Full-Time",
        "work_mode": "Hybrid",
        "source_system": "FABRIC_HR_LAKEHOUSE",
        "source_record_id": "delta:employee_history:1",
        "extracted_at": "2026-10-30T00:00:00Z",
        "source_type": "hris_production",
    }])


class FakeConnector:
    def __init__(self, frame):
        self.frame = frame

    def read_history(self, context):
        return self.frame.copy()


def _context():
    return SourceReadContext(
        source_system="FABRIC_HR_LAKEHOUSE",
        extracted_at="2026-10-30T00:00:00Z",
        watermark="2026-10-29T23:59:59Z",
    )


def test_connector_result_is_validated_and_returns_aggregate_report():
    result = read_governed_history(FakeConnector(_frame()), _context())
    assert result.report["connector_validation"] == "pass"
    assert result.report["source_record_count"] == 1
    assert result.report["employee_level_values_emitted"] is False
    assert result.history.iloc[0]["employee_id"] == "E001"


def test_connector_source_identity_must_match_context():
    context = SourceReadContext("OTHER_HRIS", "2026-10-30T00:00:00Z")
    with pytest.raises(HrisHistorySourceError, match="does not match"):
        validate_connector_result(_frame(), context)


def test_connector_extract_timestamp_must_match_context():
    context = SourceReadContext("FABRIC_HR_LAKEHOUSE", "2026-10-31T00:00:00Z")
    with pytest.raises(HrisHistorySourceError, match="timestamp does not match"):
        validate_connector_result(_frame(), context)


def test_provider_failure_is_sanitized():
    class BrokenConnector:
        def read_history(self, context):
            raise RuntimeError("sensitive endpoint and token details")

    with pytest.raises(HrisHistorySourceError, match="failed to read history") as error:
        read_governed_history(BrokenConnector(), _context())
    assert "token" not in str(error.value)
