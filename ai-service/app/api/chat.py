
"""Deterministic HR analytics question answering."""
from typing import Any
from app.data.kpi_engine import list_kpis
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
def answer_question(question: str, gold: Any, period: str | None = None) -> dict[str, Any]:
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
    from app.data.kpi_engine import compute_kpi
    result = compute_kpi(kpi_name, gold, period=period)
    if result.value is None:
        message = (
            f"{result.display_name} is unavailable for the selected data "
            "because its value could not be calculated."
        )
    elif result.unit == "ratio":
        message = (
            f"{result.display_name} is {result.value:.4f} "
            f"as a ratio ({result.value * 100:.2f}% when expressed as a percentage). "
            "This follows the repository's DAX definition."
        )
    elif result.unit == "percent":
        message = f"{result.display_name} is {result.value * 100:.2f}%."
    elif result.unit == "days":
        message = f"{result.display_name} is {result.value:.2f} days."
    elif result.unit == "years":
        message = f"{result.display_name} is {result.value:.2f} years."
    else:
        message = f"{result.display_name} is {result.value}."
    return {
        "status": "ok",
        "question": question,
        "matched_phrase": matched_phrase,
        "answer": message,
        "evidence": result.as_dict(),
    }
