"""Deterministic HR KPI calculations on Gold-equivalent frames."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any
import pandas as pd
import yaml
from app.data.csv_gold import (
    GoldTables,
    month_end,
    rolling_12m_month_ends,
)
CATALOG_PATH = Path(__file__).resolve().parents[1] / "catalog" / "kpi_catalog.yaml"
VALID_PERIODS = ("all", "rolling_12m", "latest_month")
class UnknownKpiError(Exception):
    def __init__(self, name: str, known: list[str]):
        self.name = name
        self.known = known
        super().__init__(f"Unknown KPI '{name}'.")
class InvalidPeriodError(Exception):
    def __init__(self, period: str):
        self.period = period
        super().__init__(f"Invalid period '{period}'. Use one of: {', '.join(VALID_PERIODS)}.")
@dataclass
class KpiResult:
    name: str
    display_name: str
    category: str
    value: float | int | None
    unit: str
    numerator: float | int | None
    denominator: float | int | None
    denominator_zero: bool
    as_of: date
    period: str
    definition: str
    definition_source: str
    conflicts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "category": self.category,
            "value": _json_number(self.value),
            "unit": self.unit,
            "numerator": _json_number(self.numerator),
            "denominator": _json_number(self.denominator),
            "denominator_zero": self.denominator_zero,
            "as_of": self.as_of.isoformat(),
            "period": self.period,
            "definition": self.definition,
            "definition_source": self.definition_source,
            "conflicts": self.conflicts,
            "notes": self.notes,
        }
def _json_number(value: float | int | None) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value
@lru_cache(maxsize=1)
def load_catalog() -> list[dict[str, Any]]:
    with CATALOG_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return list(data["kpis"])
def catalog_by_name() -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in load_catalog()}
def list_kpis() -> list[dict[str, Any]]:
    return [
        {
            "name": item["name"],
            "display_name": item["display_name"],
            "category": item["category"],
            "unit": item["unit"],
            "default_period": item["default_period"],
            "definition": item["definition"],
            "definition_source": item["definition_source"],
            "conflicts": item.get("conflicts") or [],
        }
        for item in load_catalog()
    ]
def _safe_divide(numerator: float | int, denominator: float | int) -> tuple[float | None, bool]:
    if denominator == 0:
        return None, True
    return float(numerator) / float(denominator), False
def _month_spine(start: date, end: date) -> list[date]:
    """Calendar month-ends from start month through end month, inclusive."""
    months: list[date] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        months.append(month_end(cursor))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return months


def _missing_snapshot_note(filtered: pd.DataFrame, months: list[date]) -> str | None:
    if not months:
        return None
    observed = {
        pd.to_datetime(value).date()
        for value in filtered["month_end"].dropna().unique().tolist()
    } if not filtered.empty else set()
    missing = [month.isoformat() for month in months if month not in observed]
    if not missing:
        return None
    return (
        "Missing monthly headcount snapshot(s): "
        + ", ".join(missing)
        + ". Average headcount uses observed months only; missing snapshots are not treated as zero."
    )


def _filter_headcount(gold: GoldTables, period: str) -> tuple[pd.DataFrame, list[date]]:
    hc = gold.headcount_monthly
    if hc.empty:
        return hc, []
    as_of_me = month_end(gold.as_of)
    if period == "all":
        hc = hc.loc[pd.to_datetime(hc["month_end"]).dt.date <= as_of_me].copy()
        if hc.empty:
            return hc, []
        first_month = min(pd.to_datetime(hc["month_end"]).dt.date)
        months = _month_spine(first_month, as_of_me)
        return hc, months
    if period == "latest_month":
        months = [as_of_me]
        return hc.loc[hc["month_end"] == as_of_me].copy(), months
    if period == "rolling_12m":
        months = rolling_12m_month_ends(gold.as_of)
        return hc.loc[hc["month_end"].isin(months)].copy(), months
    raise InvalidPeriodError(period)
def _hires_exits(filtered: pd.DataFrame, flag: str) -> int:
    if filtered.empty:
        return 0
    return int(filtered.loc[filtered[flag], "employee_id"].nunique())
def _average_headcount(filtered: pd.DataFrame, months: list[date]) -> float:
    if filtered.empty:
        return 0.0
    monthly = filtered.groupby("month_end")["employee_id"].nunique()
    if monthly.empty:
        return 0.0
    return float(monthly.mean())
def _exits_in_period(gold: GoldTables, period: str) -> pd.DataFrame:
    ex = gold.exits
    if ex.empty:
        return ex
    as_of_me = month_end(gold.as_of)
    if period == "all":
        return ex
    if period == "latest_month":
        ms = date(as_of_me.year, as_of_me.month, 1)
        lwd = pd.to_datetime(ex["last_working_date"], errors="coerce")
        mask = (lwd.dt.date >= ms) & (lwd.dt.date <= as_of_me)
        return ex.loc[mask].copy()
    if period == "rolling_12m":
        months = rolling_12m_month_ends(gold.as_of)
        start = months[0].replace(day=1) if months else as_of_me
        lwd = pd.to_datetime(ex["last_working_date"], errors="coerce")
        mask = (lwd.dt.date >= start) & (lwd.dt.date <= months[-1])
        return ex.loc[mask].copy()
    raise InvalidPeriodError(period)
def compute_kpi(name: str, gold: GoldTables, period: str | None = None) -> KpiResult:
    catalog = catalog_by_name()
    if name not in catalog:
        raise UnknownKpiError(name, sorted(catalog))
    spec = catalog[name]
    resolved_period = period or spec["default_period"]
    if resolved_period == "snapshot":
        resolved_period = "all"
    if resolved_period not in VALID_PERIODS:
        raise InvalidPeriodError(resolved_period)
    hc, months = _filter_headcount(gold, resolved_period if spec["default_period"] != "snapshot" else "all")
    # Snapshot KPIs ignore period filters except as_of encoded in GoldTables.
    if spec["default_period"] == "snapshot":
        resolved_period = "snapshot"
        hc, months = gold.headcount_monthly, sorted(
            gold.headcount_monthly["month_end"].unique().tolist()
        ) if not gold.headcount_monthly.empty else []
    notes: list[str] = []
    if name in {
        "hires", "exits", "net_headcount_change", "average_headcount",
        "attrition_pct", "attrition_pct_rolling_12m",
    }:
        coverage_note = _missing_snapshot_note(hc, months)
        if coverage_note:
            notes.append(coverage_note)
    numerator: float | int | None = None
    denominator: float | int | None = None
    denom_zero = False
    value: float | int | None = None
    active = gold.employees.loc[gold.employees["is_active"]] if not gold.employees.empty else gold.employees
    if name == "active_employees":
        value = int(active["employee_id"].nunique()) if not active.empty else 0
        numerator = value
    elif name == "headcount":
        latest = gold.headcount_monthly
        last = month_end(gold.as_of)
        observed_months = (
            set(pd.to_datetime(latest["month_end"]).dt.date)
            if not latest.empty else set()
        )
        if last not in observed_months:
            # Missing snapshot is unknown, not a genuine zero headcount.
            value = None
            notes.append(
                f"Missing monthly headcount snapshot for {last.isoformat()}; "
                "headcount is unknown and is not reported as zero."
            )
        else:
            slice_ = latest.loc[
                (pd.to_datetime(latest["month_end"]).dt.date == last)
                & (latest["is_month_end_active"])
            ]
            value = int(slice_["employee_id"].nunique())
        numerator = value
        resolved_period = "latest_month"
    elif name == "hires":
        value = _hires_exits(hc, "is_new_hire")
        numerator = value
    elif name == "exits":
        value = _hires_exits(hc, "is_exit")
        numerator = value
    elif name == "net_headcount_change":
        h = _hires_exits(hc, "is_new_hire")
        x = _hires_exits(hc, "is_exit")
        value = h - x
        numerator = h
        denominator = x
    elif name == "average_headcount":
        value = _average_headcount(hc, months)
        numerator = value
        denominator = len(hc["month_end"].unique()) if not hc.empty else 0
        denom_zero = denominator == 0
        if denom_zero:
            value = None
    elif name == "attrition_pct":
        exits = _hires_exits(hc, "is_exit")
        avg_hc = _average_headcount(hc, months)
        value, denom_zero = _safe_divide(exits, avg_hc)
        numerator = exits
        denominator = avg_hc
    elif name == "attrition_pct_rolling_12m":
        hc12, months12 = _filter_headcount(gold, "rolling_12m")
        exits = _hires_exits(hc12, "is_exit")
        avg_hc = _average_headcount(hc12, months12)
        value, denom_zero = _safe_divide(exits, avg_hc)
        numerator = exits
        denominator = avg_hc
        resolved_period = "rolling_12m"
    elif name == "female_pct":
        n_active = int(active["employee_id"].nunique()) if not active.empty else 0
        n_female = (
            int(active.loc[active["gender"] == "Female", "employee_id"].nunique()) if not active.empty else 0
        )
        value, denom_zero = _safe_divide(n_female, n_active)
        numerator = n_female
        denominator = n_active
        resolved_period = "snapshot"
    elif name == "avg_tenure_yrs":
        if active.empty or active["tenure_years"].dropna().empty:
            value, denom_zero = None, True
            numerator = None
            denominator = 0
        else:
            tenure = pd.to_numeric(active["tenure_years"], errors="coerce").dropna()
            value = float(tenure.mean())
            numerator = value
            denominator = int(tenure.shape[0])
        resolved_period = "snapshot"
    elif name == "regrettable_exits":
        use_period = period or "all"
        ex = _exits_in_period(gold, use_period)
        value = int((ex["regrettable_flag"] == "Y").sum()) if not ex.empty else 0
        numerator = value
        resolved_period = use_period
    elif name == "applicants":
        value = int(len(gold.recruitment))
        numerator = value
        resolved_period = "all"
    elif name == "offers":
        rec = gold.recruitment
        value = int(rec["is_offered"].fillna(False).sum()) if not rec.empty else 0
        numerator = value
        resolved_period = "all"
    elif name == "candidates_hired":
        rec = gold.recruitment
        value = int(rec["is_hired"].fillna(False).sum()) if not rec.empty else 0
        numerator = value
        resolved_period = "all"
    elif name == "offer_acceptance_pct":
        rec = gold.recruitment
        hired = int(rec["is_hired"].fillna(False).sum()) if not rec.empty else 0
        offered = int(rec["is_offered"].fillna(False).sum()) if not rec.empty else 0
        value, denom_zero = _safe_divide(hired, offered)
        numerator = hired
        denominator = offered
        resolved_period = "all"
    elif name == "applicant_to_hire_pct":
        rec = gold.recruitment
        hired = int(rec["is_hired"].fillna(False).sum()) if not rec.empty else 0
        apps = int(len(rec))
        value, denom_zero = _safe_divide(hired, apps)
        numerator = hired
        denominator = apps
        resolved_period = "all"
    elif name == "avg_time_to_hire_days":
        days = pd.to_numeric(
            gold.recruitment.get("time_to_hire_days"),
            errors="coerce",
        ).dropna()
        negative_count = int((days < 0).sum())
        valid_days = days[days >= 0]
        if valid_days.empty:
            value, denom_zero = None, True
            denominator = 0
            numerator = None
        else:
            value = float(valid_days.mean())
            denominator = int(valid_days.shape[0])
            numerator = value
            denom_zero = False
        resolved_period = "all"
        if negative_count:
            notes.append(
                f"Data-quality warning: excluded {negative_count} "
                "negative time-to-hire durations because hire dates "
                "precede application dates."
            )
        notes.append(
            "Average of non-null, non-negative time-to-hire durations. Negative durations are excluded and reported as data-quality issues."
        )
    elif name == "avg_time_to_fill_days":
        days = pd.to_numeric(gold.recruitment.get("time_to_fill_days"), errors="coerce")
        days = days.dropna()
        if days.empty:
            value, denom_zero = None, True
            denominator = 0
        else:
            value = float(days.mean())
            denominator = int(days.shape[0])
        numerator = value
        resolved_period = "all"
        notes.append("Null time_to_fill_days (no employee candidate_id link) are excluded from the average.")
    else:
        raise UnknownKpiError(name, sorted(catalog))
    if gold.quarantined_employee_count:
        notes.append(
            f"{gold.quarantined_employee_count} employee rows quarantined (invalid department or dates); excluded from Gold."
        )
    return KpiResult(
        name=name,
        display_name=spec["display_name"],
        category=spec["category"],
        value=value,
        unit=spec["unit"],
        numerator=numerator,
        denominator=denominator,
        denominator_zero=denom_zero,
        as_of=gold.as_of,
        period=resolved_period,
        definition=spec["definition"],
        definition_source=spec["definition_source"],
        conflicts=list(spec.get("conflicts") or []),
        notes=notes,
    )
