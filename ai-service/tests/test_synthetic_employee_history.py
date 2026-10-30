from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data.employee_history import validate_employee_history, point_in_time_employee_attributes
from app.data.synthetic_employee_history import build_synthetic_employee_history


def _employees():
    return pd.DataFrame([
        {"employee_id": "E100", "hire_date": date(2020, 1, 1), "department_id": "D02", "location_id": "L02", "grade_id": "G2", "employment_type": "Full-Time", "work_mode": "Remote"},
        {"employee_id": "E101", "hire_date": date(2023, 1, 1), "department_id": "D01", "location_id": "L01", "grade_id": "G1", "employment_type": "Contract", "work_mode": "Hybrid"},
    ])


def test_generator_is_deterministic_and_explicitly_synthetic():
    first = build_synthetic_employee_history(_employees(), date(2025, 12, 31))
    second = build_synthetic_employee_history(_employees(), date(2025, 12, 31))
    pd.testing.assert_frame_equal(first, second)
    assert set(first["source_type"]) == {"synthetic_demo"}
    assert validate_employee_history(first)["status"] == "pass"


def test_generated_history_resolves_attributes_for_hire_and_asof_snapshots():
    history = build_synthetic_employee_history(_employees(), date(2025, 12, 31))
    snapshots = pd.DataFrame([
        {"employee_id": "E100", "snapshot_date": "2020-01-31"},
        {"employee_id": "E100", "snapshot_date": "2025-12-31"},
        {"employee_id": "E101", "snapshot_date": "2023-01-31"},
    ])
    resolved = point_in_time_employee_attributes(snapshots, history)
    assert len(resolved) == len(snapshots)
    assert resolved["department_id"].notna().all()
