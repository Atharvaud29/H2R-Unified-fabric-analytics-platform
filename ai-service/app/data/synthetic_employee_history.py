"""Deterministic synthetic history generator for pipeline demonstrations only."""
from __future__ import annotations

import hashlib
from calendar import monthrange
from datetime import date, datetime, time, timezone
from typing import Any

import pandas as pd

from app.data.employee_history import ATTRIBUTE_COLUMNS, HISTORY_COLUMNS, validate_employee_history


def _add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def build_synthetic_employee_history(
    employees: pd.DataFrame,
    as_of: date,
) -> pd.DataFrame:
    """Create deterministic fictional attribute transitions anchored to current demo rows.

    These values are fabricated test fixtures, not reconstructed HRIS events.
    Every output row carries source_type='synthetic_demo'.
    """
    required = {"employee_id", "hire_date", *ATTRIBUTE_COLUMNS}
    missing = sorted(required.difference(employees.columns))
    if missing:
        raise ValueError("Employees missing columns required for synthetic history: " + ", ".join(missing))

    categories = {
        column: sorted(
            value for value in employees[column].dropna().astype(str).str.strip().unique()
            if value and value.lower() != "nan"
        )
        for column in ATTRIBUTE_COLUMNS
    }
    rows: list[dict[str, Any]] = []
    for employee in employees.sort_values("employee_id").itertuples(index=False):
        employee_id = str(employee.employee_id).strip()
        hire = pd.to_datetime(employee.hire_date, errors="coerce")
        if pd.isna(hire) or hire.date() > as_of:
            continue
        hire_date = hire.date()
        current = {
            column: str(getattr(employee, column)).strip()
            if pd.notna(getattr(employee, column)) and str(getattr(employee, column)).strip()
            else "Unknown"
            for column in ATTRIBUTE_COLUMNS
        }
        digest = hashlib.sha256(employee_id.encode("utf-8")).digest()
        tenure_months = max(0, (as_of.year - hire_date.year) * 12 + as_of.month - hire_date.month)
        make_transition = tenure_months >= 18 and digest[0] % 2 == 0
        transition_date = _add_months(hire_date, max(1, (tenure_months * 2) // 3)) if make_transition else None
        if transition_date is not None and transition_date > as_of:
            transition_date = None

        states: list[tuple[date, date | None, dict[str, str]]] = []
        if transition_date is not None:
            previous = current.copy()
            for index, column in enumerate(ATTRIBUTE_COLUMNS):
                options = categories[column]
                if len(options) > 1:
                    current_value_index = options.index(current[column]) if current[column] in options else 0
                    previous[column] = options[(current_value_index + 1 + (digest[index + 1] % (len(options) - 1))) % len(options)]
            states.append((hire_date, transition_date, previous))
            states.append((transition_date, None, current))
        else:
            states.append((hire_date, None, current))

        for start, end, attributes in states:
            recorded = datetime.combine(start, time.min, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            row = {
                "employee_id": employee_id,
                "effective_start_date": start.isoformat(),
                "effective_end_date": end.isoformat() if end else "",
                "recorded_at": recorded,
                "superseded_at": "",
                **attributes,
                "source_type": "synthetic_demo",
            }
            rows.append(row)

    columns = [*HISTORY_COLUMNS, "source_type"]
    result = pd.DataFrame(rows, columns=columns)
    if not result.empty:
        report = validate_employee_history(result)
        if report["status"] != "pass":
            raise ValueError("Generated synthetic employee history failed bitemporal validation.")
    return result
