"""Provider-neutral HRIS source connector contracts.

Concrete providers must implement read_history() and return the governed
metadata columns alongside the canonical bitemporal attributes. Authentication
and network clients belong in provider-specific implementations, never here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from app.data.hris_history_source import (
    HrisHistorySourceError,
    validate_governed_hris_history_frame,
)


@dataclass(frozen=True)
class SourceReadContext:
    """Non-secret context for one bounded source extraction."""

    source_system: str
    extracted_at: str
    watermark: str | None = None


@dataclass(frozen=True)
class SourceReadResult:
    """Validated source rows and aggregate-only extraction metadata."""

    history: pd.DataFrame
    report: dict[str, Any]


@runtime_checkable
class HrisHistoryConnector(Protocol):
    """Contract implemented by Fabric, database, or HRIS provider adapters."""

    def read_history(self, context: SourceReadContext) -> pd.DataFrame:
        """Return canonical history columns plus source lineage metadata."""
        ...


def validate_connector_result(
    frame: pd.DataFrame,
    context: SourceReadContext,
) -> SourceReadResult:
    """Enforce source identity and extraction context before feature ingestion."""
    history, report = validate_governed_hris_history_frame(frame)
    if report["source_system"] != context.source_system:
        raise HrisHistorySourceError(
            "Connector source_system does not match the configured extraction context."
        )
    if report["extract_timestamp"] != pd.Timestamp(context.extracted_at).tz_convert("UTC").isoformat():
        raise HrisHistorySourceError(
            "Connector extract timestamp does not match the configured extraction context."
        )
    report["connector_validation"] = "pass"
    report["watermark_present"] = context.watermark is not None
    return SourceReadResult(history=history, report=report)


def read_governed_history(
    connector: HrisHistoryConnector,
    context: SourceReadContext,
) -> SourceReadResult:
    """Read once from a connector and validate before returning data downstream."""
    try:
        frame = connector.read_history(context)
    except HrisHistorySourceError:
        raise
    except Exception as exc:
        # Do not leak provider exception text, which can contain query or endpoint details.
        raise HrisHistorySourceError("Configured HRIS connector failed to read history.") from exc
    return validate_connector_result(frame, context)
