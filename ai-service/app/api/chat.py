"""Deterministic HR analytics question answering."""
from typing import Any

from app.data.kpi_engine import compute_kpi, list_kpis


# Map common phrases to existing KPI catalog names.
QUESTION_MAP = {
    "headcount": ["headcount", "active employees", "workforce size"],
    "active_employees": ["active employees", "currently employed"],
    "attrition_pct": ["attrition", "attrition rate", "employee turnover"],
    "attrition_pct_rolling_12m": ["rolling 12 month attrition", "rolling attrition"],
    "hires": ["hires", "new hires", "employees hired"],
    "exits": ["exits", "employees left", "employees exited"],
    "female_pct": ["female percentage", "female representation", "women representation"],
    "avg_tenure_yrs": ["average tenure", "average length of service"],
    "regrettable_exits": ["regrettable exits"],
    "applicants": ["applicants", "number of applicants"],
    "offers": ["offers", "offers made"],
    "candidates_hired": ["candidates hired", "candidates who were hired"],
    "offer_acceptance_pct": ["offer acceptance", "offer acceptance rate"],
    "applicant_to_hire_pct": ["applicant to hire", "applicant-to-hire rate"],
    "avg_time_to_hire_days": ["time to hire", "average time to hire"],
    "avg_time_to_fill_days": ["time to fill", "average time to fill"],
}


def _format_value(value: float | int, unit: str) -> str:
    """Format a computed KPI without changing its underlying API unit."""
    if unit == "ratio":
        return (
            f"{value:.4f} as a ratio "
            f"({value * 100:.2f}% when expressed as a percentage)"
        )
    if unit == "percent":
        return f"{value * 100:.2f}%"
    if unit == "days":
        return f"{value:.2f} days"
    if unit == "years":
        return f"{value:.2f} years"
    return str(value)


def answer_question(question: str, gold: Any) -> dict[str, Any]:
    """Answer a supported question using calculated KPI evidence."""
    normalized = " ".join(question.lower().strip().rstrip("?.!").split())
    if not normalized:
        return {
            "status": "invalid_question",
            "message": "Please enter a question.",
        }

    supported = {item["name"] for item in list_kpis()}
    # Prefer longer phrases to avoid matching a generic word first.
    candidates = []
    for kpi_name, phrases in QUESTION_MAP.items():
        if kpi_name not in supported:
            continue
        for phrase in phrases:
            if phrase in normalized:
                candidates.append((len(phrase), kpi_name, phrase))

    if not candidates:
        return {
            "status": "unsupported_question",
            "message": (
                "I couldn't match that question to a supported HR KPI. "
                "Try asking about headcount, attrition, hires, exits, "
                "recruitment, offer acceptance, or average tenure."
            ),
            "supported_kpis": sorted(supported),
        }

    _, kpi_name, matched_phrase = max(candidates)
    result = compute_kpi(kpi_name, gold)
    evidence = result.as_dict()
    context = f"As of {result.as_of.isoformat()} (period: {result.period})."

    if result.value is None:
        message = (
            f"{result.display_name} is unavailable for the selected data "
            "because its value could not be calculated. "
            f"{context}"
        )
    else:
        message = (
            f"{result.display_name} is "
            f"{_format_value(result.value, result.unit)}. {context}"
        )

    if result.notes:
        message += " Data notes: " + " ".join(result.notes)
    if result.conflicts:
        message += (
            " Definition caveat: the KPI catalog records a definition "
            "conflict that should be reviewed before comparing this value "
            "with other reporting layers."
        )

    return {
        "status": "ok",
        "question": question,
        "matched_phrase": matched_phrase,
        "answer": message,
        "evidence": evidence,
    }
