# Phase 3.3 – Governed HRIS Historical Data Integration

## Scope

This milestone establishes the production-source contract and a strict CSV adapter for an approved effective-dated HRIS history extract. It does **not** claim that a live HRIS or Fabric Delta connection exists. No real HR data was supplied to this repository during implementation.

## Canonical source contract

One row represents one employee attribute version with two independent time axes:

| Column | Meaning |
|---|---|
| employee_id | Pseudonymous stable employee key |
| effective_start_date | Inclusive date the attributes become valid |
| effective_end_date | Exclusive end date; blank means open-ended |
| recorded_at | Inclusive UTC timestamp when HRIS recorded this version |
| superseded_at | Exclusive UTC timestamp when this version was superseded; blank means current system version |
| department_id, location_id, grade_id | Governed organization/location/grade codes |
| employment_type, work_mode | Governed employment attributes |
| source_system | Single named HRIS source for the extract |
| source_record_id | Unique immutable source event/version identifier |
| extracted_at | One timezone-aware UTC extraction timestamp shared by the file |
| source_type | Must be exactly `hris_production` |

Intervals follow `[effective_start_date, effective_end_date)` and `[recorded_at, superseded_at)`. Attribute values must be explicit; use a governed `Unknown` code where source semantics genuinely require it, not a silent null fill.

The extract must not contain names, email addresses, dates of birth, gender, free-text exit reasons, or other direct identifiers/sensitive fields. Employee identifiers should be pseudonymous and access controlled.

## Adapter behavior

`app.data.hris_history_source.load_governed_hris_history(path)`:
- Requires every canonical history and lineage column.
- Rejects empty files, missing lineage, duplicate source record IDs, mixed source systems, mixed extraction timestamps, and invalid timestamps.
- Rejects `synthetic_demo` and any provenance other than `hris_production`.
- Reuses the existing bitemporal validator and rejects overlapping versions.
- Returns normalized history plus aggregate diagnostics only.

No fallback to the current employee dimension is provided.

## Validate a supplied extract

From `ai-service`:

```bash
python scripts/validate_hris_history_source.py --input /secure/path/hris_employee_history.csv
```

Optional aggregate report:

```bash
python scripts/validate_hris_history_source.py \\
  --input /secure/path/hris_employee_history.csv \\
  --report-json artifacts/hris_history_source_validation.json
```

Do not commit real employee data, credentials, access tokens, or production extracts to Git. Supply data through an approved secure Fabric/enterprise storage connection or a protected runtime mount.

## Required integration decisions before production wiring

1. Confirm the HRIS product, authoritative history entity/table, and owner.
2. Confirm whether the source is a true change log or reconstructed snapshots.
3. Confirm valid-time and system-time semantics, timezone, correction handling, and deletion semantics.
4. Map HRIS codes to Gold dimension keys with versioned mapping tables.
5. Establish pseudonymization, RBAC, encryption, retention, audit, and legal/privacy approvals.
6. Choose the supported Fabric access path (for example, governed Lakehouse Delta table or secured export) and managed identity/secret mechanism.
7. Validate row counts, source freshness, reconciliation totals, and point-in-time coverage against an approved source period.
8. Run the Phase 3.2 point-in-time dataset validator on the real source before considering model training.

## Readiness boundary

A passing adapter test or a file labelled `hris_production` is not proof of source authenticity or approval. Source ownership, lineage, permissions, and governance must be independently attested. Until an approved real extract is supplied and reconciled, training readiness remains blocked. This adapter is a contract boundary, not a live HRIS/Fabric connector.
