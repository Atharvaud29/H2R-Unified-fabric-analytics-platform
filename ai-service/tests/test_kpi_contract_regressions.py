from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.data.csv_gold import load_gold
from app.data.kpi_engine import compute_kpi
from tests.test_kpi_engine import _write_min_csvs


def _monthly_headcount_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    months = pd.date_range("2023-12-01", "2024-12-01", freq="MS") + pd.offsets.MonthEnd(0)
    for month in months:
        month_end = month.date()
        month_key = month.strftime("%Y%m")
        for index in range(10):
            employee_id = f"E{month_key}_{index:02d}"
            rows.append(
                {
                    "month_end": month_end,
                    "employee_id": employee_id,
                    "is_new_hire": False,
                    "is_exit": (month_key == "202312" and index == 0)
                    or (month_key == "202401" and index in {0, 1}),
                    "is_month_end_active": True,
                }
            )
    return rows


@pytest.fixture
def gold_with_controlled_months(tmp_path: Path):
    _write_min_csvs(tmp_path)
    gold = load_gold(tmp_path, as_of=date(2024, 12, 31))
    gold.headcount_monthly = pd.DataFrame(_monthly_headcount_rows())
    return gold


def test_rolling_12m_attrition_excludes_month_before_window(gold_with_controlled_months):
    result = compute_kpi(
        "attrition_pct_rolling_12m", gold_with_controlled_months
    )

    # The rolling window is Jan-Dec 2024. The December 2023 exit is outside it.
    assert result.period == "rolling_12m"
    assert result.numerator == 2
    assert result.denominator == pytest.approx(10.0)
    assert result.value == pytest.approx(0.2)
    assert result.denominator_zero is False


def test_attrition_is_null_when_average_headcount_is_zero(gold_with_controlled_months):
    gold_with_controlled_months.headcount_monthly = (
        gold_with_controlled_months.headcount_monthly.iloc[0:0].copy()
    )

    result = compute_kpi("attrition_pct", gold_with_controlled_months, period="all")

    assert result.value is None
    assert result.numerator == 0
    assert result.denominator == 0.0
    assert result.denominator_zero is True


def test_offer_acceptance_exposes_hired_and_offered_counts(gold_with_controlled_months):
    result = compute_kpi("offer_acceptance_pct", gold_with_controlled_months)

    # The fixture contains one Hired candidate and two offered-or-hired candidates.
    assert result.numerator == 1
    assert result.denominator == 2
    assert result.value == pytest.approx(0.5)
    assert result.unit == "ratio"
    assert result.denominator_zero is False


def test_rate_api_contract_keeps_ratio_not_percent_points(gold_with_controlled_months):
    result = compute_kpi("attrition_pct_rolling_12m", gold_with_controlled_months)

    assert result.unit == "ratio"
    assert result.value == pytest.approx(0.2)
    assert result.as_dict()["value"] == pytest.approx(0.2)


def test_average_headcount_uses_distinct_employees_per_observed_month(
    gold_with_controlled_months,
):
    rows: list[dict[str, object]] = []
    for month_key, count in (("202410", 10), ("202411", 20), ("202412", 30)):
        month_end = pd.Timestamp(f"{month_key[:4]}-{month_key[4:]}-01") + pd.offsets.MonthEnd(0)
        for index in range(count):
            rows.append(
                {
                    "month_end": month_end.date(),
                    "employee_id": f"{month_key}_E{index:03d}",
                    "is_new_hire": False,
                    "is_exit": False,
                    "is_month_end_active": True,
                }
            )
    gold_with_controlled_months.headcount_monthly = pd.DataFrame(rows)

    result = compute_kpi(
        "average_headcount", gold_with_controlled_months, period="all"
    )

    # Monthly headcounts are 10, 20 and 30; average is 20 across 3 observed months.
    assert result.value == pytest.approx(20.0)
    assert result.numerator == pytest.approx(20.0)
    assert result.denominator == 3
    assert result.denominator_zero is False


def test_latest_month_headcount_uses_as_of_month_end(gold_with_controlled_months):
    result = compute_kpi(
        "headcount", gold_with_controlled_months, period="latest_month"
    )

    assert result.value == 10
    assert result.period == "latest_month"


def test_average_headcount_reports_missing_month_without_treating_it_as_zero(
    gold_with_controlled_months,
):
    rows = _monthly_headcount_rows()
    # Remove the entire May 2024 snapshot. The average remains over observed
    # months only, but the result must disclose the missing calendar month.
    rows = [row for row in rows if row["month_end"] != date(2024, 5, 31)]
    gold_with_controlled_months.headcount_monthly = pd.DataFrame(rows)

    result = compute_kpi(
        "average_headcount", gold_with_controlled_months, period="all"
    )

    assert result.value == pytest.approx(10.0)
    assert any(
        "2024-05-31" in note and "not treated as zero" in note
        for note in result.notes
    )

