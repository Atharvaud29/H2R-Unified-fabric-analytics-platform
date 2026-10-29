from datetime import date
from types import SimpleNamespace

from app.api import chat


def _result(*, value=12, unit="count", notes=None, conflicts=None):
    evidence = {
        "name": "headcount",
        "value": value,
        "as_of": "2024-12-31",
        "period": "latest_month",
        "notes": notes or [],
        "conflicts": conflicts or [],
    }
    return SimpleNamespace(
        name="headcount",
        display_name="Headcount",
        category="workforce",
        value=value,
        unit=unit,
        numerator=value,
        denominator=None,
        denominator_zero=False,
        as_of=date(2024, 12, 31),
        period="latest_month",
        definition="Distinct active employees at month end.",
        definition_source="DAX",
        notes=notes or [],
        conflicts=conflicts or [],
        as_dict=lambda: evidence,
    )


def test_answer_includes_as_of_period_and_structured_evidence(monkeypatch):
    monkeypatch.setattr(chat, "list_kpis", lambda: [{"name": "headcount"}])
    monkeypatch.setattr(chat, "compute_kpi", lambda name, gold: _result())

    response = chat.answer_question("What is our headcount?", object())

    assert response["status"] == "ok"
    assert "12" in response["answer"]
    assert "2024-12-31" in response["answer"]
    assert "latest_month" in response["answer"]
    assert response["evidence"]["value"] == 12


def test_answer_discloses_unavailable_value_and_data_notes(monkeypatch):
    notes = ["Missing monthly headcount snapshot for 2024-12-31."]
    monkeypatch.setattr(chat, "list_kpis", lambda: [{"name": "headcount"}])
    monkeypatch.setattr(
        chat, "compute_kpi", lambda name, gold: _result(value=None, notes=notes)
    )

    response = chat.answer_question("headcount?", object())

    assert response["status"] == "ok"
    assert "unavailable" in response["answer"]
    assert "2024-12-31" in response["answer"]
    assert "Missing monthly headcount snapshot" in response["answer"]


def test_ratio_answer_shows_ratio_and_percent_equivalent(monkeypatch):
    monkeypatch.setattr(chat, "list_kpis", lambda: [{"name": "headcount"}])
    monkeypatch.setattr(
        chat, "compute_kpi", lambda name, gold: _result(value=0.25, unit="ratio")
    )

    response = chat.answer_question("headcount?", object())

    assert "0.2500 as a ratio" in response["answer"]
    assert "25.00%" in response["answer"]


def test_answer_discloses_definition_conflict(monkeypatch):
    monkeypatch.setattr(chat, "list_kpis", lambda: [{"name": "headcount"}])
    monkeypatch.setattr(
        chat, "compute_kpi",
        lambda name, gold: _result(conflicts=["DAX and SQL formulas differ"]),
    )

    response = chat.answer_question("headcount?", object())

    assert "Definition caveat" in response["answer"]
    assert response["evidence"]["conflicts"] == ["DAX and SQL formulas differ"]


def test_unsupported_question_does_not_calculate_kpi(monkeypatch):
    monkeypatch.setattr(chat, "list_kpis", lambda: [{"name": "headcount"}])

    def fail_compute(*args, **kwargs):
        raise AssertionError("KPI should not be calculated for unsupported questions")

    monkeypatch.setattr(chat, "compute_kpi", fail_compute)
    response = chat.answer_question("Will hiring rise next year?", object())

    assert response["status"] == "unsupported_question"
    assert response["supported_kpis"] == ["headcount"]
