"""Strict validation for approved, effective-dated HRIS history extracts.

The DataFrame validator is shared by file-based and live source adapters. It
accepts only the canonical, governed contract and never infers missing history.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.data.employee_history import (
    ATTRIBUTE_COLUMNS,
    HISTORY_COLUMNS,
    EmployeeHistoryError,
    validate_employee_history,
)


SOURCE_METADATA_COLUMNS = (
    "source_system",
    "source_record_id",
    "extracted_at",
    "source_type",
)
REQUIRED_HRIS_HISTORY_COLUMNS = (*HISTORY_COLUMNS, *SOURCE_METADATA_COLUMNS)


class HrisHistorySourceError(ValueError):
    """Raised when an HRIS history extract violates the governed source contract."""


def validate_governed_hris_history_frame(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate a source DataFrame and return canonical history plus aggregate diagnostics."""
    if not isinstance(frame, pd.DataFrame):
        raise HrisHistorySourceError("HRIS source must return a pandas DataFrame.")
    raw = frame.copy()
    raw.columns = [str(column).strip().lower().replace(" ", "_") for column in raw.columns]
    missing = sorted(set(REQUIRED_HRIS_HISTORY_COLUMNS).difference(raw.columns))
    if missing:
        raise HrisHistorySourceError(
            "HRIS history extract is missing required contract columns: " + ", ".join(missing)
        )
    if raw.empty:
        raise HrisHistorySourceError("HRIS history extract contains no records.")

    source_type = raw["source_type"].astype("string").str.strip().str.lower()
    if source_type.isna().any() or not source_type.eq("hris_production").all():
        raise HrisHistorySourceError(
            "Only explicitly approved hris_production extracts are accepted; synthetic_demo is not eligible."
        )
    for column in ("source_system", "source_record_id"):
        raw[column] = raw[column].astype("string").str.strip()
        if raw[column].isna().any() or raw[column].eq("").any():
            raise HrisHistorySourceError(f"{column} must be populated for every source record.")
    if raw["source_record_id"].duplicated().any():
        raise HrisHistorySourceError("source_record_id must be unique within an extract.")
    systems = raw["source_system"].dropna().unique().tolist()
    if len(systems) != 1:
        raise HrisHistorySourceError("One extract must contain records from exactly one source_system.")

    extracted = pd.to_datetime(raw["extracted_at"], errors="coerce", utc=True)
    if extracted.isna().any():
        raise HrisHistorySourceError("extracted_at must contain valid timezone-aware timestamps.")
    if extracted.nunique() != 1:
        raise HrisHistorySourceError("All rows in one extract must share the same extracted_at timestamp.")

    history = raw.loc[:, list(HISTORY_COLUMNS)].copy()
    try:
        report = validate_employee_history(history)
    except EmployeeHistoryError as exc:
        raise HrisHistorySourceError("HRIS bitemporal history validation failed: " + str(exc)) from exc
    if report["status"] != "pass":
        raise HrisHistorySourceError(
            "HRIS bitemporal history validation failed: overlapping versions detected."
        )

    report.update({
        "source_type": "hris_production",
        "source_system": systems[0],
        "extract_timestamp": extracted.iloc[0].isoformat(),
        "source_record_count": int(len(raw)),
        "required_attribute_count": len(ATTRIBUTE_COLUMNS),
        "employee_level_values_emitted": False,
    })
    return history, report


def load_governed_hris_history(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load and validate an approved HRIS history CSV; return normalized history + aggregate report."""
    source_path = Path(path)
    if not source_path.is_file():
        raise HrisHistorySourceError("Configured HRIS history file does not exist.")
    try:
        raw = pd.read_csv(source_path, dtype="string")
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise HrisHistorySourceError("HRIS history extract could not be read as a CSV.") from exc
    return validate_governed_hris_history_frame(raw)
