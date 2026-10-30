"""Build Gold-equivalent frames from sample-data CSVs.

Transformations follow notebooks/02_silver_transformation.ipynb and
notebooks/03_gold_dimensional_model.ipynb using only columns present in
sample-data. This is a local pandas stand-in for Fabric Delta tables.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import pandas as pd

from app.data.employee_history import EmployeeHistoryError, validate_employee_history
REQUIRED_FILES = (
    "hris_employees.csv",
    "hris_departments.csv",
    "hris_exits.csv",
    "ats_candidates.csv",
    "ats_requisitions.csv",
)
STAGE_ORDER = {
    "Applied": 1,
    "Screened": 2,
    "Interviewed": 3,
    "Offered": 4,
    "Hired": 5,
}
class CsvGoldError(Exception):
    """Raised when source CSVs are missing or unusable."""
@dataclass
class GoldTables:
    as_of: date
    employees: pd.DataFrame
    quarantined_employee_count: int
    headcount_monthly: pd.DataFrame
    recruitment: pd.DataFrame
    exits: pd.DataFrame
    employee_history: pd.DataFrame | None = None
def month_end(d: date) -> date:
    if d.month == 12:
        nxt = date(d.year + 1, 1, 1)
    else:
        nxt = date(d.year, d.month + 1, 1)
    return nxt.fromordinal(nxt.toordinal() - 1)
def month_start(d: date) -> date:
    return date(d.year, d.month, 1)
def month_ends_through(as_of: date, start: date | None = None) -> list[date]:
    end = month_end(as_of)
    cursor = month_end(start or date(as_of.year, as_of.month, 1))
    if start is None:
        cursor = end
        out = [end]
        return out
    out: list[date] = []
    cur = month_end(start)
    while cur <= end:
        out.append(cur)
        if cur.month == 12:
            nxt_first = date(cur.year + 1, 1, 1)
        else:
            nxt_first = date(cur.year, cur.month + 1, 1)
        cur = month_end(nxt_first)
    return out
def add_months(d: date, months: int) -> date:
    idx = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(idx, 12)
    return date(year, month0 + 1, min(d.day, 28) if d.day > 28 else d.day)
def rolling_12m_month_ends(as_of: date) -> list[date]:
    end = month_end(as_of)
    start = month_end(add_months(date(end.year, end.month, 1), -11))
    return month_ends_through(end, start)
def months_between(end: pd.Series, start: pd.Series) -> pd.Series:
    """Approximate Spark months_between used in Silver tenure_years."""
    end_dt = pd.to_datetime(end)
    start_dt = pd.to_datetime(start)
    return (
        (end_dt.dt.year - start_dt.dt.year) * 12
        + (end_dt.dt.month - start_dt.dt.month)
        + (end_dt.dt.day - start_dt.dt.day) / 31.0
    )
def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
    return out
def _parse_dates(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.date
    return out
def map_gender(series: pd.Series) -> pd.Series:
    cleaned = series.fillna("").astype(str).str.strip().str.lower()
    return cleaned.map(
        {
            "m": "Male",
            "male": "Male",
            "f": "Female",
            "female": "Female",
            "non-binary": "Non-binary",
            "nb": "Non-binary",
        }
    ).fillna("Not Disclosed")
def default_as_of(sample_data_dir: Path) -> date:
    """Last date present in source files, not the machine clock.

    Gold notebook 03 filters month_end <= last_day(current_date()). Local
    tests must not depend on today's date, so as_of defaults to max observed
    hire/termination/applied/opened dates.
    """
    dates: list[date] = []
    files_cols = {
        "hris_employees.csv": ["hire_date", "termination_date"],
        "hris_exits.csv": ["last_working_date"],
        "ats_candidates.csv": ["applied_date"],
        "ats_requisitions.csv": ["opened_date"],
    }
    for name, cols in files_cols.items():
        path = sample_data_dir / name
        if not path.exists():
            continue
        df = _normalise_columns(pd.read_csv(path, usecols=lambda c: True))
        df = _parse_dates(df, [c for c in cols if c in df.columns])
        for col in cols:
            if col in df.columns:
                dates.extend(v for v in df[col].dropna().tolist())
    if not dates:
        raise CsvGoldError("Could not infer as_of: no dated rows in sample-data CSVs.")
    return max(dates)
def missing_source_files(sample_data_dir: Path) -> list[str]:
    return [name for name in REQUIRED_FILES if not (sample_data_dir / name).exists()]
def _read_csv(sample_data_dir: Path, name: str) -> pd.DataFrame:
    path = sample_data_dir / name
    if not path.exists():
        raise CsvGoldError(f"Required source file not found: {name}")
    df = _normalise_columns(pd.read_csv(path))
    if df.empty and name == "hris_employees.csv":
        raise CsvGoldError("hris_employees.csv contains no rows.")
    return df
def silver_employees(raw: pd.DataFrame, departments: pd.DataFrame, as_of: date) -> tuple[pd.DataFrame, int]:
    emp = raw.copy()
    needed = ["employee_id", "department_id", "gender", "hire_date", "termination_date"]
    missing = [c for c in needed if c not in emp.columns]
    if missing:
        raise CsvGoldError("hris_employees.csv missing required columns.")
    emp["employee_id"] = emp["employee_id"].astype(str).str.strip().str.upper()
    emp["department_id"] = emp["department_id"].astype(str).str.strip().str.upper()
    emp["gender"] = map_gender(emp["gender"])
    emp = _parse_dates(emp, ["hire_date", "termination_date", "date_of_birth"])
    if "candidate_id" in emp.columns:
        emp["candidate_id"] = emp["candidate_id"].where(emp["candidate_id"].notna(), None)
        emp["candidate_id"] = emp["candidate_id"].replace({pd.NA: None, "nan": None, "": None})
    else:
        emp["candidate_id"] = None
    emp = emp.drop_duplicates(subset=["employee_id"], keep="first")
    valid_depts = set(departments["department_id"].astype(str).str.strip().str.upper())
    invalid_dept = ~emp["department_id"].isin(valid_depts)
    bad_hire = emp["hire_date"].isna()
    term_before_hire = emp["termination_date"].notna() & (emp["termination_date"] < emp["hire_date"])
    bad = invalid_dept | bad_hire | term_before_hire
    quarantined = int(bad.sum())
    emp = emp.loc[~bad].copy()
    as_of_date = emp["termination_date"].where(emp["termination_date"].notna(), as_of)
    emp["tenure_years"] = (months_between(as_of_date, emp["hire_date"]) / 12).round(1)
    emp["is_active"] = emp["termination_date"].isna()
    return emp, quarantined
def fact_headcount_monthly(employees: pd.DataFrame, as_of: date) -> pd.DataFrame:
    if employees.empty:
        return pd.DataFrame(
            columns=[
                "month_end",
                "employee_id",
                "is_new_hire",
                "is_exit",
                "is_month_end_active",
            ]
        )
    hire_min = min(d for d in employees["hire_date"] if pd.notna(d))
    months = month_ends_through(as_of, hire_min)
    rows = []
    for me in months:
        ms = month_start(me)
        for rec in employees.itertuples(index=False):
            hire = rec.hire_date
            term = rec.termination_date
            if pd.isna(hire) or hire > me:
                continue
            if pd.notna(term) and term < ms:
                continue
            is_new = month_start(hire) == ms
            is_exit = pd.notna(term) and month_start(term) == ms
            is_active = pd.isna(term) or term > me
            rows.append(
                {
                    "month_end": me,
                    "employee_id": rec.employee_id,
                    "is_new_hire": bool(is_new),
                    "is_exit": bool(is_exit),
                    "is_month_end_active": bool(is_active),
                }
            )
    return pd.DataFrame(rows)
def fact_recruitment(
    candidates: pd.DataFrame,
    requisitions: pd.DataFrame,
    employees: pd.DataFrame,
) -> pd.DataFrame:
    cand = candidates.copy()
    if "candidate_id" not in cand.columns:
        raise CsvGoldError("ats_candidates.csv missing candidate_id.")
    cand["candidate_id"] = cand["candidate_id"].astype(str).str.strip()
    cand = cand.drop_duplicates(subset=["candidate_id"], keep="first")
    cand = _parse_dates(cand, ["applied_date"])
    cand["current_stage"] = cand.get("current_stage", pd.Series(index=cand.index, dtype=object))
    cand["stage_order"] = cand["current_stage"].map(STAGE_ORDER)
    req = requisitions.copy()
    if "requisition_id" in req.columns:
        req = _parse_dates(req, ["opened_date"])
        req = req.drop_duplicates(subset=["requisition_id"], keep="first")
        cand = cand.merge(
            req[["requisition_id", "opened_date"]] if "opened_date" in req.columns else req[["requisition_id"]],
            on="requisition_id",
            how="left",
        )
    else:
        cand["opened_date"] = pd.NaT
    hires = employees.loc[employees["candidate_id"].notna(), ["candidate_id", "employee_id", "hire_date"]].copy()
    hires["candidate_id"] = hires["candidate_id"].astype(str)
    cand = cand.merge(hires, on="candidate_id", how="left")
    hire_dates = pd.to_datetime(cand["hire_date"], errors="coerce")
    applied = pd.to_datetime(cand["applied_date"], errors="coerce")
    opened = pd.to_datetime(cand["opened_date"], errors="coerce")
    cand["is_hired"] = cand["current_stage"] == "Hired"
    cand["is_offered"] = cand["stage_order"].fillna(0) >= 4
    cand["time_to_hire_days"] = (hire_dates - applied).dt.days
    cand["time_to_fill_days"] = (hire_dates - opened).dt.days
    return cand
def fact_exit(exits_raw: pd.DataFrame, employees: pd.DataFrame) -> pd.DataFrame:
    ex = exits_raw.copy()
    if "employee_id" not in ex.columns:
        raise CsvGoldError("hris_exits.csv missing employee_id.")
    ex["employee_id"] = ex["employee_id"].astype(str).str.strip().str.upper()
    ex = _parse_dates(ex, ["last_working_date", "resignation_date"])
    emp_keys = employees[["employee_id", "hire_date", "department_id"]].drop_duplicates("employee_id")
    ex = ex.merge(emp_keys, on="employee_id", how="left")
    if "regrettable_flag" in ex.columns:
        ex["regrettable_flag"] = ex["regrettable_flag"].astype(str).str.strip().str.upper()
    else:
        ex["regrettable_flag"] = None
    if "exit_type" in ex.columns:
        ex["exit_type"] = ex["exit_type"].astype(str).str.strip()
    tenure = months_between(ex["last_working_date"], ex["hire_date"]) / 12
    ex["tenure_at_exit_years"] = tenure.round(1)
    return ex
def load_gold(sample_data_dir: Path, as_of: date | None = None) -> GoldTables:
    sample_data_dir = Path(sample_data_dir)
    missing = missing_source_files(sample_data_dir)
    if missing:
        raise CsvGoldError("Missing required CSV files: " + ", ".join(missing))
    as_of = as_of or default_as_of(sample_data_dir)
    departments = _read_csv(sample_data_dir, "hris_departments.csv")
    if "department_id" not in departments.columns:
        raise CsvGoldError("hris_departments.csv missing department_id.")
    departments["department_id"] = departments["department_id"].astype(str).str.strip().str.upper()
    employees, quarantined = silver_employees(
        _read_csv(sample_data_dir, "hris_employees.csv"),
        departments,
        as_of,
    )
    recruitment = fact_recruitment(
        _read_csv(sample_data_dir, "ats_candidates.csv"),
        _read_csv(sample_data_dir, "ats_requisitions.csv"),
        employees,
    )
    exits = fact_exit(_read_csv(sample_data_dir, "hris_exits.csv"), employees)
    headcount = fact_headcount_monthly(employees, as_of)
    history_path = sample_data_dir / "hris_employee_history_synthetic.csv"
    employee_history = None
    if history_path.exists():
        employee_history = _normalise_columns(pd.read_csv(history_path))
        if "source_type" not in employee_history.columns or not employee_history["source_type"].eq("synthetic_demo").all():
            raise CsvGoldError("The demo history source must explicitly identify every row as synthetic_demo.")
        report = validate_employee_history(employee_history)
        if report["status"] != "pass":
            raise CsvGoldError("Employee history failed bitemporal validation: " + "; ".join(report["errors"]))
    return GoldTables(
        as_of=as_of,
        employees=employees,
        quarantined_employee_count=quarantined,
        headcount_monthly=headcount,
        recruitment=recruitment,
        exits=exits,
        employee_history=employee_history,
    )
def infer_as_of_from_value(value: str | date | datetime | None, sample_data_dir: Path) -> date:
    if value is None:
        return default_as_of(sample_data_dir)
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise CsvGoldError("as_of must be YYYY-MM-DD.") from exc
