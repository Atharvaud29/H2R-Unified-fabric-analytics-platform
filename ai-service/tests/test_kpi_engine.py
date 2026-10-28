from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data.csv_gold import CsvGoldError, load_gold, map_gender, silver_employees
from app.data.kpi_engine import UnknownKpiError, compute_kpi


def _write_min_csvs(tmp_path: Path) -> Path:
    """Tiny synthetic extract using only columns that exist in sample-data."""
    pd.DataFrame(
        [
            {"department_id": "D01", "department_name": "Engineering", "business_unit": "Technology"},
        ]
    ).to_csv(tmp_path / "hris_departments.csv", index=False)

    pd.DataFrame(
        [
            {
                "employee_id": "E000001",
                "first_name": "Ada",
                "last_name": "Lee",
                "gender": "Female",
                "date_of_birth": "1990-01-01",
                "hire_date": "2024-01-15",
                "department_id": "D01",
                "location_id": "L01",
                "grade_id": "G1",
                "employment_type": "Full-Time",
                "work_mode": "Hybrid",
                "candidate_id": "CAN000001",
                "manager_id": None,
                "termination_date": None,
                "employment_status": "Active",
                "email": "ada.lee.0001@h2r-demo.example",
            },
            {
                "employee_id": "E000002",
                "first_name": "Ben",
                "last_name": "Shah",
                "gender": "Male",
                "date_of_birth": "1988-06-01",
                "hire_date": "2024-01-15",
                "department_id": "D01",
                "location_id": "L01",
                "grade_id": "G1",
                "employment_type": "Full-Time",
                "work_mode": "Hybrid",
                "candidate_id": None,
                "manager_id": None,
                "termination_date": "2024-06-20",
                "employment_status": "Exited",
                "email": "ben.shah.0002@h2r-demo.example",
            },
            {
                "employee_id": "E000003",
                "first_name": "Cam",
                "last_name": "Patel",
                "gender": "m",
                "date_of_birth": "1992-03-01",
                "hire_date": "2023-01-10",
                "department_id": "d01",
                "location_id": "L01",
                "grade_id": "G2",
                "employment_type": "Full-Time",
                "work_mode": "On-site",
                "candidate_id": None,
                "manager_id": None,
                "termination_date": None,
                "employment_status": "Active",
                "email": "cam.patel.0003@h2r-demo.example",
            },
            # duplicate of E000001 (Silver de-duplicates)
            {
                "employee_id": "E000001",
                "first_name": "Ada",
                "last_name": "Lee",
                "gender": "Female",
                "date_of_birth": "1990-01-01",
                "hire_date": "2024-01-15",
                "department_id": "D01",
                "location_id": "L01",
                "grade_id": "G1",
                "employment_type": "Full-Time",
                "work_mode": "Hybrid",
                "candidate_id": "CAN000001",
                "manager_id": None,
                "termination_date": None,
                "employment_status": "Active",
                "email": "ada.lee.0001@h2r-demo.example",
            },
            # quarantined: invalid department
            {
                "employee_id": "E000099",
                "first_name": "Zed",
                "last_name": "Void",
                "gender": "Male",
                "date_of_birth": "1991-01-01",
                "hire_date": "2024-02-01",
                "department_id": "D99",
                "location_id": "L01",
                "grade_id": "G1",
                "employment_type": "Full-Time",
                "work_mode": "Hybrid",
                "candidate_id": None,
                "manager_id": None,
                "termination_date": None,
                "employment_status": "Active",
                "email": "zed.void.0099@h2r-demo.example",
            },
            # quarantined: termination before hire
            {
                "employee_id": "E000098",
                "first_name": "Yan",
                "last_name": "Bad",
                "gender": "Female",
                "date_of_birth": "1991-01-01",
                "hire_date": "2024-06-01",
                "department_id": "D01",
                "location_id": "L01",
                "grade_id": "G1",
                "employment_type": "Full-Time",
                "work_mode": "Hybrid",
                "candidate_id": None,
                "manager_id": None,
                "termination_date": "2024-01-01",
                "employment_status": "Exited",
                "email": "yan.bad.0098@h2r-demo.example",
            },
        ]
    ).to_csv(tmp_path / "hris_employees.csv", index=False)

    pd.DataFrame(
        [
            {
                "employee_id": "E000002",
                "resignation_date": "2024-05-01",
                "last_working_date": "2024-06-20",
                "exit_type": "Voluntary",
                "exit_reason": "Better Opportunity",
                "regrettable_flag": "Y",
                "kt_completed": "Y",
                "exit_interview_score": 3.2,
            }
        ]
    ).to_csv(tmp_path / "hris_exits.csv", index=False)

    pd.DataFrame(
        [
            {
                "requisition_id": "REQ00001",
                "department_id": "D01",
                "location_id": "L01",
                "grade_id": "G1",
                "opened_date": "2023-12-01",
                "requisition_status": "Filled",
            }
        ]
    ).to_csv(tmp_path / "ats_requisitions.csv", index=False)

    pd.DataFrame(
        [
            {
                "candidate_id": "CAN000001",
                "requisition_id": "REQ00001",
                "source_channel": "LinkedIn",
                "gender": "Female",
                "applied_date": "2023-12-10",
                "current_stage": "Hired",
                "offer_status": "Accepted",
            },
            {
                "candidate_id": "CAN000002",
                "requisition_id": "REQ00001",
                "source_channel": "Campus",
                "gender": "Male",
                "applied_date": "2023-12-15",
                "current_stage": "Offered",
                "offer_status": "Pending",
            },
            {
                "candidate_id": "CAN000003",
                "requisition_id": "REQ00001",
                "source_channel": "Job Portal",
                "gender": "Female",
                "applied_date": "2023-12-20",
                "current_stage": "Applied",
                "offer_status": None,
            },
            {
                "candidate_id": "CAN000004",
                "requisition_id": "REQ00001",
                "source_channel": "Referral",
                "gender": None,
                "applied_date": None,
                "current_stage": None,
                "offer_status": None,
            },
        ]
    ).to_csv(tmp_path / "ats_candidates.csv", index=False)
    return tmp_path


@pytest.fixture
def gold(tmp_path: Path):
    return load_gold(_write_min_csvs(tmp_path), as_of=date(2024, 12, 31))


def test_gender_standardisation():
    series = pd.Series(["M", " female", "nb", None, "unknown"])
    mapped = map_gender(series)
    assert mapped.tolist() == ["Male", "Female", "Non-binary", "Not Disclosed", "Not Disclosed"]


def test_quarantine_and_dedupe(tmp_path: Path):
    gold = load_gold(_write_min_csvs(tmp_path), as_of=date(2024, 12, 31))
    ids = set(gold.employees["employee_id"])
    assert ids == {"E000001", "E000002", "E000003"}
    assert gold.quarantined_employee_count == 2
    assert gold.employees["employee_id"].is_unique
    cam = gold.employees.loc[gold.employees["employee_id"] == "E000003"].iloc[0]
    assert cam["department_id"] == "D01"
    assert cam["gender"] == "Male"


def test_active_employees_and_female_pct(gold):
    active = compute_kpi("active_employees", gold)
    assert active.value == 2
    female = compute_kpi("female_pct", gold)
    assert female.numerator == 1
    assert female.denominator == 2
    assert female.value == 0.5
    assert female.denominator_zero is False


def test_headcount_hires_exits(gold):
    hc = compute_kpi("headcount", gold)
    assert hc.value == 2
    assert hc.period == "latest_month"
    hires = compute_kpi("hires", gold, period="all")
    assert hires.value == 3
    exits = compute_kpi("exits", gold, period="all")
    assert exits.value == 1
    net = compute_kpi("net_headcount_change", gold, period="all")
    assert net.value == 2


def test_attrition_pct_matches_exits_over_average_headcount(gold):
    result = compute_kpi("attrition_pct", gold, period="all")
    exits = compute_kpi("exits", gold, period="all").value
    avg = compute_kpi("average_headcount", gold, period="all").value
    assert result.numerator == exits
    assert result.denominator == avg
    assert result.value == pytest.approx(exits / avg)
    assert "vw_monthly_workforce_movement.monthly_attrition_pct" in " ".join(result.conflicts)


def test_recruitment_kpis(gold):
    assert compute_kpi("applicants", gold).value == 4
    assert compute_kpi("offers", gold).value == 2
    assert compute_kpi("candidates_hired", gold).value == 1
    offer_acc = compute_kpi("offer_acceptance_pct", gold)
    assert offer_acc.value == pytest.approx(0.5)
    conv = compute_kpi("applicant_to_hire_pct", gold)
    assert conv.value == pytest.approx(0.25)
    tth = compute_kpi("avg_time_to_hire_days", gold)
    assert tth.value == pytest.approx(36)
    ttf = compute_kpi("avg_time_to_fill_days", gold)
    assert ttf.value == pytest.approx(45)

def test_avg_time_to_hire_excludes_negative_durations(gold):
    gold.recruitment = gold.recruitment.iloc[:4].copy()
    gold.recruitment["time_to_hire_days"] = [-10, 0, 10, 20]

    result = compute_kpi("avg_time_to_hire_days", gold)

    assert result.value == pytest.approx(10)
    assert result.denominator == 3
    assert any(
        "negative" in note.lower() and "excluded" in note.lower()
        for note in result.notes
    )

def test_zero_denominator_offer_acceptance(tmp_path: Path):
    _write_min_csvs(tmp_path)
    pd.DataFrame(
        [
            {
                "candidate_id": "CANX",
                "requisition_id": "REQ00001",
                "source_channel": "Campus",
                "gender": "Male",
                "applied_date": "2023-12-15",
                "current_stage": "Applied",
                "offer_status": None,
            }
        ]
    ).to_csv(tmp_path / "ats_candidates.csv", index=False)
    gold = load_gold(tmp_path, as_of=date(2024, 12, 31))
    result = compute_kpi("offer_acceptance_pct", gold)
    assert result.value is None
    assert result.denominator_zero is True
    assert result.denominator == 0


def test_missing_values_do_not_break_averages(gold):
    tth = compute_kpi("avg_time_to_hire_days", gold)
    assert tth.denominator == 1
    assert tth.value is not None
    female = compute_kpi("female_pct", gold)
    assert female.value is not None


def test_unknown_kpi(gold):
    with pytest.raises(UnknownKpiError) as exc:
        compute_kpi("not_a_kpi", gold)
    assert "active_employees" in exc.value.known


def test_missing_csv_raises(tmp_path: Path):
    with pytest.raises(CsvGoldError):
        load_gold(tmp_path, as_of=date(2024, 12, 31))


def test_null_hire_date_quarantined():
    departments = pd.DataFrame([{"department_id": "D01"}])
    raw = pd.DataFrame(
        [
            {
                "employee_id": "E1",
                "department_id": "D01",
                "gender": "Male",
                "hire_date": None,
                "termination_date": None,
            }
        ]
    )
    emp, quarantined = silver_employees(raw, departments, date(2024, 12, 31))
    assert quarantined == 1
    assert emp.empty


def test_regrettable_exits(gold):
    assert compute_kpi("regrettable_exits", gold).value == 1
