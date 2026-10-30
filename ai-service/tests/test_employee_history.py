from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import pytest
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from app.data.employee_history import EmployeeHistoryError, point_in_time_employee_attributes, validate_employee_history

def _history():
    return pd.DataFrame([
        {"employee_id":"E001","effective_start_date":"2022-01-01","effective_end_date":"2023-07-01","recorded_at":"2022-01-01T08:00:00Z","superseded_at":None,"department_id":"D01","location_id":"L01","grade_id":"G2","employment_type":"Full-Time","work_mode":"Hybrid"},
        {"employee_id":"E001","effective_start_date":"2023-07-01","effective_end_date":None,"recorded_at":"2023-07-01T08:00:00Z","superseded_at":None,"department_id":"D02","location_id":"L01","grade_id":"G3","employment_type":"Full-Time","work_mode":"Remote"},
    ])

def test_point_in_time_join_uses_snapshot_valid_department():
    snapshots=pd.DataFrame([{"employee_id":"E001","snapshot_date":"2023-06-30"},{"employee_id":"E001","snapshot_date":"2023-07-31"}])
    result=point_in_time_employee_attributes(snapshots,_history())
    assert result["department_id"].tolist()==["D01","D02"]
    assert result["work_mode"].tolist()==["Hybrid","Remote"]

def test_future_recorded_change_is_not_visible_at_earlier_snapshot():
    history=_history()
    history.loc[1,"recorded_at"]="2023-08-05T08:00:00Z"
    snapshots=pd.DataFrame([{"employee_id":"E001","snapshot_date":"2023-07-31"}])
    with pytest.raises(EmployeeHistoryError,match="exactly one"):
        point_in_time_employee_attributes(snapshots,history)

def test_rejects_overlapping_versions_known_at_same_time():
    history=_history()
    history.loc[0,"effective_end_date"]="2023-09-01"
    report=validate_employee_history(history)
    assert report["status"]=="fail"
    assert report["overlapping_bitemporal_versions"]==1

def test_allows_retroactive_correction_when_system_periods_do_not_overlap():
    history=pd.DataFrame([
        {"employee_id":"E001","effective_start_date":"2022-01-01","effective_end_date":None,"recorded_at":"2022-01-01T08:00:00Z","superseded_at":"2023-08-01T08:00:00Z","department_id":"D01","location_id":"L01","grade_id":"G2","employment_type":"Full-Time","work_mode":"Hybrid"},
        {"employee_id":"E001","effective_start_date":"2022-01-01","effective_end_date":None,"recorded_at":"2023-08-01T08:00:00Z","superseded_at":None,"department_id":"D02","location_id":"L01","grade_id":"G2","employment_type":"Full-Time","work_mode":"Hybrid"},
    ])
    assert validate_employee_history(history)["status"]=="pass"

def test_rejects_missing_history_instead_of_falling_back():
    snapshots=pd.DataFrame([{"employee_id":"E999","snapshot_date":"2023-06-30"}])
    with pytest.raises(EmployeeHistoryError,match="exactly one"):
        point_in_time_employee_attributes(snapshots,_history())

def test_rejects_invalid_effective_interval():
    history=_history()
    history.loc[0,"effective_end_date"]="2021-12-31"
    with pytest.raises(EmployeeHistoryError,match="effective_end_date"):
        validate_employee_history(history)
