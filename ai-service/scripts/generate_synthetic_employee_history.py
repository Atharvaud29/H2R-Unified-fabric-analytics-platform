"""Generate a clearly labelled synthetic HRIS history CSV.

Run from ai-service:
    python scripts/generate_synthetic_employee_history.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(AI_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_ROOT))

from app.config import Settings
from app.data.csv_gold import infer_as_of_from_value, load_gold
from app.data.synthetic_employee_history import build_synthetic_employee_history
from app.data.employee_history import validate_employee_history


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate labelled synthetic employee history.")
    parser.add_argument("--sample-data-dir", type=Path, default=None)
    parser.add_argument("--as-of", default=None, help="Source cutoff date (YYYY-MM-DD).")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path; defaults to sample-data/hris_employee_history_synthetic.csv.",
    )
    args = parser.parse_args()

    sample_dir = args.sample_data_dir or Settings().resolved_sample_data_dir()
    as_of = infer_as_of_from_value(args.as_of, sample_dir)
    gold = load_gold(sample_dir, as_of=as_of)
    history = build_synthetic_employee_history(gold.employees, as_of)
    output = args.output or (sample_dir / "hris_employee_history_synthetic.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(output, index=False)
    report = validate_employee_history(history)
    print("Source type: synthetic_demo (fabricated; not observed HRIS history)")
    print(f"As-of date: {as_of.isoformat()}")
    print(f"Output: {output.resolve()}")
    print(f"History rows: {report['history_rows']}")
    print(f"Employees: {report['distinct_employees']}")
    print(f"Bitemporal conflicts: {report['overlapping_bitemporal_versions']}")
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
