"""Validate a provider connector in an approved runtime.

No live provider is configured by this repository phase. Provider adapters
should call this shared validation boundary before handing data to Phase 3.4.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(AI_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_ROOT))

from app.data.hris_history_source import HrisHistorySourceError, load_governed_hris_history


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a governed HRIS history extract.")
    parser.add_argument("--history-path", type=Path, required=True)
    parser.add_argument("--expected-source-system", required=True)
    parser.add_argument("--expected-extracted-at", required=True)
    args = parser.parse_args()

    try:
        history, report = load_governed_hris_history(args.history_path)
        expected_at = datetime.fromisoformat(args.expected_extracted_at.replace("Z", "+00:00"))
        actual_at = datetime.fromisoformat(report["extract_timestamp"].replace("Z", "+00:00"))
        if report["source_system"] != args.expected_source_system:
            raise HrisHistorySourceError("Extract source_system does not match the expected source.")
        if expected_at != actual_at:
            raise HrisHistorySourceError("Extract timestamp does not match the expected extraction context.")
    except (HrisHistorySourceError, ValueError) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, sort_keys=True))
        return 2

    safe_report = {
        key: report[key]
        for key in (
            "status", "source_type", "source_system", "extract_timestamp",
            "source_record_count", "distinct_employees",
            "overlapping_bitemporal_versions", "employee_level_values_emitted",
        )
    }
    safe_report["status"] = "pass"
    print(json.dumps(safe_report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
