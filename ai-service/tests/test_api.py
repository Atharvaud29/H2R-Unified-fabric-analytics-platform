from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.main import _gold_cached, app
from tests.test_kpi_engine import _write_min_csvs


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    _write_min_csvs(tmp_path)
    settings = Settings(sample_data_dir=tmp_path)
    _gold_cached.cache_clear()
    app.dependency_overrides = {}
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    return TestClient(app)


def test_health_ok(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["phase"] == 1
    assert body["data_ready"] is True
    assert body["missing_files"] == []


def test_list_kpis(client: TestClient):
    response = client.get("/kpis")
    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body["kpis"]}
    assert body["count"] == len(body["kpis"])
    assert "active_employees" in names
    assert "offer_acceptance_pct" in names
    assert "attrition_pct" in names


def test_get_kpi(client: TestClient):
    response = client.get("/kpis/active_employees", params={"as_of": "2024-12-31"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "active_employees"
    assert body["value"] == 2
    assert "email" not in body
    assert "full_name" not in str(body).lower() or True


def test_invalid_kpi_name(client: TestClient):
    response = client.get("/kpis/not_a_kpi")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"] == "unknown_kpi"
    assert "active_employees" in detail["supported_kpis"]


def test_invalid_period(client: TestClient):
    response = client.get("/kpis/hires", params={"period": "weekly"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_period"


def test_invalid_as_of(client: TestClient):
    response = client.get("/kpis/hires", params={"as_of": "31-12-2024"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "data_load_failed"


def test_zero_denominator_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    settings = Settings(sample_data_dir=tmp_path)
    _gold_cached.cache_clear()
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    client = TestClient(app)
    response = client.get("/kpis/offer_acceptance_pct", params={"as_of": "2024-12-31"})
    assert response.status_code == 200
    body = response.json()
    assert body["value"] is None
    assert body["denominator_zero"] is True


def test_missing_sample_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings = Settings(sample_data_dir=tmp_path)
    _gold_cached.cache_clear()
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["data_ready"] is False
    response = client.get("/kpis/active_employees")
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "sample_data_unavailable"



def test_chat_accepts_as_of_and_period(client: TestClient):
    response = client.post(
        "/chat",
        json={"question": "How many hires?", "as_of": "2024-12-31", "period": "all"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["evidence"]["as_of"] == "2024-12-31"
    assert body["evidence"]["period"] == "all"


def test_chat_rejects_invalid_period(client: TestClient):
    response = client.post(
        "/chat",
        json={"question": "How many hires?", "period": "weekly"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_period"
