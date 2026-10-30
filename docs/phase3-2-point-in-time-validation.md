# Phase 3.2 – Point-in-Time Feature Dataset Integration and Validation

## Objective

Independently verify that the employee-month attrition dataset is temporally correct, reproducible from Gold inputs, leakage-aware, and safe to progress to a governed training-data review.

## What is validated

The Phase 2 feature contract remains unchanged:

- Metadata: `employee_id`, `snapshot_date`
- Model features: department, location, grade, employment type, work mode, tenure, hire month, snapshot month, snapshot quarter
- Target: `exit_within_horizon`

The Phase 3.1.1 bitemporal resolver is used again independently by the validator. For every employee-month row, it recomputes the five historical categorical attributes and compares them with the dataset. It also independently recomputes:

- Forward exit labels using `last_working_date` in `(snapshot_date, snapshot_date + horizon_days]`
- Tenure and hire-month values from hire date
- Snapshot month and quarter
- Active employee-month membership from Gold headcount
- Full observability of the forward label horizon
- Month-end snapshot grain, unique employee-month keys, null features, and binary target values

The validator emits aggregate counts only; it does not print employee IDs or feature rows.

## Run locally

From `ai-service`:

```bash
python scripts/generate_synthetic_employee_history.py
python scripts/validate_point_in_time_dataset.py --horizon-days 90
```

Optional aggregate JSON report:

```bash
python scripts/validate_point_in_time_dataset.py --horizon-days 90 --report-json artifacts/point_in_time_validation.json
```

Use `--sample-data-dir` and `--as-of YYYY-MM-DD` to select another local source directory or source cutoff.

## Pass criteria

- Exact declared dataset schema; identifiers remain metadata, not model features.
- Exactly one bitemporal history version resolves for each snapshot.
- Zero historical attribute mismatches against a fresh point-in-time lookup.
- Zero forward-label mismatches against exit events.
- Zero tenure/calendar feature mismatches.
- Every row maps to an active Gold employee-month snapshot.
- Every snapshot has a fully observable forward horizon.
- No duplicate employee-month keys, null model features, invalid targets, or non-month-end snapshots.

A report can technically pass with a single target class, but it will mark supervised binary training as not ready.

## Provenance and production boundary

The repository generator creates `synthetic_demo` history because the supplied sample HRIS employee file is current-state data, not an observed effective-dated change log. A passing synthetic report demonstrates the mechanics and regression checks only. It is explicitly marked `synthetic_demo_only_not_production_ready`.

Production readiness requires an approved HRIS history feed with trustworthy effective dates and recorded/system timestamps, source lineage, access controls, privacy/legal review, retention controls, subgroup/fairness evaluation, and human oversight. Do not use synthetic history or model scores as a basis for individual employment decisions.

## CI integration

GitHub Actions runs the new validator after generating the labelled synthetic history. The validator exits non-zero when any temporal, label, schema, or quality check fails.
