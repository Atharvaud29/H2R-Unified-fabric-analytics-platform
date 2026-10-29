
"""Phase 1 FastAPI app: local, deterministic HR KPIs from synthetic CSVs."""

from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.chat import answer_question
from app.config import Settings, get_settings
from app.data.csv_gold import (
    CsvGoldError,
    GoldTables,
    infer_as_of_from_value,
    load_gold,
    missing_source_files,
    REQUIRED_FILES,
)
from app.data.kpi_engine import (
    InvalidPeriodError,
    UnknownKpiError,
    compute_kpi,
    list_kpis,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("h2r-ai-service")

app = FastAPI(
    title="H2R AI Analytics Service",
    description="Phase 1: read-only HR KPIs computed from repository sample-data CSVs.",
    version="0.1.0",
)


def _source_fingerprint(sample_data_dir: str) -> str:
    """Fingerprint required CSV contents so edits cannot leave stale cached KPIs."""
    digest = hashlib.sha256()
    root = __import__("pathlib").Path(sample_data_dir)
    for filename in REQUIRED_FILES:
        path = root / filename
        digest.update(filename.encode("utf-8"))
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=8)
def _gold_cached(sample_data_dir: str, as_of_iso: str, source_fingerprint: str) -> GoldTables:
    from datetime import date as date_cls

    as_of = date_cls.fromisoformat(as_of_iso)
    logger.info("Loading Gold-equivalent frames from CSV as_of=%s", as_of_iso)
    return load_gold(sample_data_dir, as_of=as_of)


def _load(settings: Settings, as_of: str | None) -> GoldTables:
    sample_dir = settings.resolved_sample_data_dir()
    missing = missing_source_files(sample_dir)
    if missing:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "sample_data_unavailable",
                "message": "Required synthetic CSV files were not found.",
                "missing_files": missing,
            },
        )
    try:
        resolved = infer_as_of_from_value(as_of, sample_dir)
        return _gold_cached(str(sample_dir), resolved.isoformat(), _source_fingerprint(str(sample_dir)))
    except CsvGoldError as exc:
        raise HTTPException(
            status_code=400 if "as_of" in str(exc) else 503,
            detail={"error": "data_load_failed", "message": str(exc)},
        ) from exc


@app.get("/health")
def health() -> dict[str, Any]:
    cfg = get_settings()
    sample_dir = cfg.resolved_sample_data_dir()
    missing = missing_source_files(sample_dir)
    payload = {
        "status": "ok",
        "service": "h2r-ai-service",
        "phase": 1,
        "sample_data_dir": str(sample_dir),
        "data_ready": not missing,
        "missing_files": missing,
    }
    logger.info("health data_ready=%s missing_count=%s", payload["data_ready"], len(missing))
    return payload


@app.get("/kpis")
def get_kpis() -> dict[str, Any]:
    items = list_kpis()
    return {"count": len(items), "kpis": items}


@app.get("/kpis/{name}")
def get_kpi(
    name: str,
    as_of: str | None = Query(default=None, description="ISO date YYYY-MM-DD; default is max date in CSVs."),
    period: str | None = Query(
        default=None,
        description="all | rolling_12m | latest_month. Ignored for snapshot KPIs.",
    ),
) -> JSONResponse:
    if period is not None and period not in {"all", "rolling_12m", "latest_month"}:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_period",
                "message": "period must be one of: all, rolling_12m, latest_month.",
            },
        )
    cfg = get_settings()
    gold = _load(cfg, as_of)
    try:
        result = compute_kpi(name, gold, period=period)
    except UnknownKpiError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "unknown_kpi",
                "message": f"KPI '{name}' is not supported in Phase 1.",
                "supported_kpis": exc.known,
            },
        ) from exc
    except InvalidPeriodError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_period", "message": str(exc)},
        ) from exc
    logger.info(
        "kpi name=%s period=%s as_of=%s denominator_zero=%s",
        result.name,
        result.period,
        result.as_of.isoformat(),
        result.denominator_zero,
    )
    return JSONResponse(result.as_dict())



class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    as_of: str | None = Field(default=None, description="Optional ISO date YYYY-MM-DD.")
    period: str | None = Field(default=None, description="Optional KPI period: all, rolling_12m, or latest_month.")


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=422,
            detail="Question must not be empty.",
        )

    if request.period is not None and request.period not in {"all", "rolling_12m", "latest_month"}:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_period",
                "message": "period must be one of: all, rolling_12m, latest_month.",
            },
        )

    gold = _load(get_settings(), request.as_of)
    return answer_question(question, gold, period=request.period)
