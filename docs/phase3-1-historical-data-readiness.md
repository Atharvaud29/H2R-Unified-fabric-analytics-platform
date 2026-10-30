# Phase 3.1 – Historical Data Readiness

## Objective

Make attrition training examples point-in-time correct. For an employee snapshot at date S, model features must represent attributes that were both effective on S (valid time) and recorded in the source system no later than the end of S (system/knowledge time). A current-state dim_employee row joined to old monthly snapshots does not satisfy this requirement.

## Findings from the current repository

- sample-data/hris_employees.csv is one row per employee and contains current department, location, grade, employment type, work mode, hire date and termination date.
- The Silver notebook deduplicates employees by employee_id; it does not retain attribute-change history.
- Gold notebook 03 builds dim_employee from the current Silver employee row.
- fact_headcount_monthly is generated using current employee attributes; it does not resolve historical employee states.
- The CSV Gold adapter mirrors this current-state behavior.
- No effective-dated employee attribute source or HRIS change-event feed is present in the repository sample files.

Therefore Phase 2's sample dataset is technically generated and structurally validated, but historical categorical features are not point-in-time validated. Do not describe it as production-training ready.

## Canonical bitemporal contract

Create/maintain hris_employee_history with one version per employee attribute state:

| Column | Type | Rule |
|---|---|---|
| employee_id | string | Required employee business key |
| effective_start_date | date | Inclusive valid-time start |
| effective_end_date | date, nullable | Exclusive valid-time end; null means open |
| recorded_at | UTC timestamp | When this version first became known to HRIS |
| superseded_at | UTC timestamp, nullable | Exclusive system-time end; null means current version |
| department_id | string | Required; use governed Unknown code if genuinely unknown |
| location_id | string | Required |
| grade_id | string | Required |
| employment_type | string | Required |
| work_mode | string | Required |

Both intervals are half-open: [start, end). The two time axes are necessary: an HR correction entered in August but backdated to July must not appear in a June/July model snapshot created before the correction was known.

## Required invariants

- effective_end_date > effective_start_date when populated.
- superseded_at > recorded_at when populated.
- No two versions for an employee may overlap in both valid time and system time.
- Every training snapshot must resolve to exactly one version.
- Missing or ambiguous matches fail closed; never fall back to current dim_employee.
- Preserve source event IDs, source system, ingestion batch and audit metadata in Fabric even though they are outside the minimal model contract.
- Retain change history; do not overwrite prior versions.

## Implementation delivered

ai-service/app/data/employee_history.py provides schema/type normalization, bitemporal overlap validation, a strict point-in-time attribute join, and fail-closed behavior when a snapshot has zero or multiple matches.

ai-service/tests/test_employee_history.py covers changes over time, late-arriving retroactive corrections, overlaps, missing history and invalid intervals.

## Fabric implementation plan

1. Add an append-preserving Bronze HRIS employee-change feed or periodic employee-history extract.
2. Build silver_employee_history with normalized keys, dates, UTC timestamps and source audit fields.
3. Build a Gold dim_employee_history Delta table using the bitemporal contract.
4. Update fact_headcount_monthly (or the AI feature query) to resolve attributes by both snapshot valid time and recorded/known time.
5. Reconcile employee-month snapshots against exactly one history version; quarantine unmatched/ambiguous rows.
6. Rebuild attrition features from the historical dimension and compare old vs corrected aggregate distributions.
7. Only then mark the training dataset point-in-time ready.

## Current readiness status

BLOCKED – source history is not present. The point-in-time utility is implemented and unit-tested, but the repository's synthetic HRIS source has no effective-dated change records. Do not fabricate history from current values, infer changes, or silently treat current attributes as historical truth.

The next required input is a genuine (for this project, synthetic-but-explicitly-generated) HRIS employee-history/change-event source with effective dates and recorded timestamps. If synthetic data is used, generate it as a distinct, auditable source feed and label it synthetic; do not backfill current employee rows as if they were observed history.
