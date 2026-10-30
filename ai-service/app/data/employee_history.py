"""Bitemporal employee attribute history and point-in-time joins."""
from __future__ import annotations
from datetime import date, datetime, time
from typing import Any
import pandas as pd

HISTORY_COLUMNS = ("employee_id", "effective_start_date", "effective_end_date", "recorded_at", "superseded_at", "department_id", "location_id", "grade_id", "employment_type", "work_mode")
ATTRIBUTE_COLUMNS = ("department_id", "location_id", "grade_id", "employment_type", "work_mode")
SNAPSHOT_KEY_COLUMNS = ("employee_id", "snapshot_date")

class EmployeeHistoryError(ValueError):
    """Raised when historical employee records are invalid or ambiguous."""

def _timestamp(values: pd.Series, field: str, nullable: bool = False) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    if not nullable and parsed.isna().any():
        raise EmployeeHistoryError(f"{field} contains missing or invalid timestamps.")
    return parsed

def normalize_employee_history(history: pd.DataFrame) -> pd.DataFrame:
    """Validate schema and normalize a copy of the bitemporal history."""
    missing = sorted(set(HISTORY_COLUMNS).difference(history.columns))
    if missing:
        raise EmployeeHistoryError("Employee history is missing required columns: " + ", ".join(missing))
    out = history.loc[:, HISTORY_COLUMNS].copy()
    out["employee_id"] = out["employee_id"].astype("string").str.strip()
    if out["employee_id"].isna().any() or out["employee_id"].eq("").any():
        raise EmployeeHistoryError("employee_id must be populated.")
    for column in ("effective_start_date", "effective_end_date"):
        parsed = pd.to_datetime(out[column], errors="coerce")
        if column == "effective_start_date" and parsed.isna().any():
            raise EmployeeHistoryError("effective_start_date contains missing or invalid dates.")
        out[column] = parsed.map(lambda value: None if pd.isna(value) else value.date()).astype(object)
    out["recorded_at"] = _timestamp(out["recorded_at"], "recorded_at")
    out["superseded_at"] = _timestamp(out["superseded_at"], "superseded_at", nullable=True)
    bad_valid = pd.Series(\n        [end is not None and end <= start for start, end in zip(out["effective_start_date"], out["effective_end_date"])],\n        index=out.index,\n    )\n    bad_system = out["superseded_at"].notna() & (out["superseded_at"] <= out["recorded_at"])
    if bad_valid.any():
        raise EmployeeHistoryError("effective_end_date must be later than effective_start_date (exclusive end).")
    if bad_system.any():
        raise EmployeeHistoryError("superseded_at must be later than recorded_at (exclusive end).")
    for column in ATTRIBUTE_COLUMNS:
        out[column] = out[column].astype("string").str.strip()
        if out[column].isna().any() or out[column].eq("").any():
            raise EmployeeHistoryError(f"{column} must be populated; use an explicit Unknown code if unavailable.")
    if out.duplicated(list(HISTORY_COLUMNS[:5])).any():
        raise EmployeeHistoryError("Duplicate employee history version keys were detected.")
    return out

def validate_employee_history(history: pd.DataFrame) -> dict[str, Any]:
    """Return aggregate diagnostics; overlapping bitemporal versions fail."""
    normalized = normalize_employee_history(history)
    conflicts = 0
    for _, group in normalized.groupby("employee_id"):
        rows = group.to_dict("records")
        for index, left in enumerate(rows):
            left_valid_end = left["effective_end_date"] if left["effective_end_date"] is not None else date.max
            left_system_end = left["superseded_at"] or pd.Timestamp.max.tz_localize("UTC")
            for right in rows[index + 1:]:
                right_valid_end = right["effective_end_date"] if right["effective_end_date"] is not None else date.max
                right_system_end = right["superseded_at"] or pd.Timestamp.max.tz_localize("UTC")
                valid_overlap = left["effective_start_date"] < right_valid_end and right["effective_start_date"] < left_valid_end
                system_overlap = left["recorded_at"] < right_system_end and right["recorded_at"] < left_system_end
                if valid_overlap and system_overlap:
                    conflicts += 1
    return {
        "status": "pass" if conflicts == 0 else "fail",
        "history_rows": int(len(normalized)),
        "distinct_employees": int(normalized["employee_id"].nunique()),
        "overlapping_bitemporal_versions": int(conflicts),
        "valid_time_convention": "[effective_start_date, effective_end_date)",
        "system_time_convention": "[recorded_at, superseded_at)",
        "errors": [] if conflicts == 0 else ["Multiple employee attribute versions are simultaneously valid and known."],
    }

def point_in_time_employee_attributes(snapshots: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """Attach attributes valid and known at each snapshot; never fall back to current state."""
    missing = sorted(set(SNAPSHOT_KEY_COLUMNS).difference(snapshots.columns))
    if missing:
        raise EmployeeHistoryError("Snapshots are missing required columns: " + ", ".join(missing))
    normalized = normalize_employee_history(history)
    source = snapshots.loc[:, SNAPSHOT_KEY_COLUMNS].copy()
    source["employee_id"] = source["employee_id"].astype("string").str.strip()
    parsed = pd.to_datetime(source["snapshot_date"], errors="coerce")
    if parsed.isna().any():
        raise EmployeeHistoryError("snapshot_date contains missing or invalid dates.")
    source["snapshot_date"] = parsed.dt.date
    if source.duplicated(list(SNAPSHOT_KEY_COLUMNS)).any():
        raise EmployeeHistoryError("Duplicate employee snapshot keys were detected.")
    matches = []
    for snapshot in source.itertuples(index=False):
        cutoff = pd.Timestamp(datetime.combine(snapshot.snapshot_date, time.max), tz="UTC")
        rows = normalized.loc[normalized["employee_id"] == snapshot.employee_id]
        selected = rows.loc[
            rows["effective_start_date"].le(snapshot.snapshot_date)
            & (rows["effective_end_date"].isna() | rows["effective_end_date"].gt(snapshot.snapshot_date))
            & rows["recorded_at"].le(cutoff)
            & (rows["superseded_at"].isna() | rows["superseded_at"].gt(cutoff))
        ]
        if len(selected) != 1:
            raise EmployeeHistoryError(
                "Each employee snapshot must match exactly one point-in-time history version; "
                f"found {len(selected)} for one snapshot."
            )
        matches.append({column: selected.iloc[0][column] for column in ATTRIBUTE_COLUMNS})
    return source.reset_index(drop=True).join(pd.DataFrame(matches, columns=ATTRIBUTE_COLUMNS))
