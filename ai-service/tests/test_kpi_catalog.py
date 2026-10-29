from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data.kpi_engine import catalog_by_name, list_kpis, load_catalog


REQUIRED_FIELDS = {
    "name",
    "display_name",
    "category",
    "unit",
    "default_period",
    "definition",
    "definition_source",
}


def test_kpi_catalog_has_unique_names_and_required_contract_fields():
    catalog = load_catalog()
    names = [item.get("name") for item in catalog]

    assert catalog
    assert all(isinstance(name, str) and name.strip() for name in names)
    assert len(names) == len(set(names))

    for item in catalog:
        assert REQUIRED_FIELDS <= item.keys(), item.get("name")
        assert item["category"] in {"workforce", "recruitment"}
        assert item["unit"] in {"count", "ratio", "years", "days"}
        assert item["default_period"] in {"snapshot", "all", "rolling_12m", "latest_month"}
        assert isinstance(item["definition"], str) and item["definition"].strip()
        assert isinstance(item["definition_source"], str) and item["definition_source"].strip()


def test_catalog_lookup_and_public_listing_have_same_kpi_names():
    by_name = catalog_by_name()
    public_names = {item["name"] for item in list_kpis()}

    assert set(by_name) == public_names
    assert len(by_name) == len(load_catalog())


@pytest.mark.parametrize(
    "name",
    [
        "attrition_pct",
        "attrition_pct_rolling_12m",
        "female_pct",
        "offer_acceptance_pct",
        "applicant_to_hire_pct",
    ],
)
def test_rate_kpis_are_documented_as_ratios_not_percent_points(name: str):
    spec = catalog_by_name()[name]

    # API values are fractions (e.g. 0.25), not 25 percent points.
    assert spec["unit"] == "ratio"
    assert "not multiplied by 100" in spec["definition"].lower() or name != "attrition_pct"
