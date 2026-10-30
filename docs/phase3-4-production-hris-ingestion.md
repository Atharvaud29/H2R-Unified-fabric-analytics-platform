# Phase 3.4 – Governed HRIS History into Attrition Feature Engineering

## Objective

Connect the Phase 3.3 governed history adapter to the existing leakage-aware feature builder. This phase introduces a selectable source path while preserving the current synthetic demo workflow for local regression tests.

This is a file-based integration boundary, not a live Workday, SAP SuccessFactors, Darwinbox, or Fabric connector. The production source must first be delivered as the Phase 3.3 canonical CSV through an approved secure runtime mount.

## Data flow

1. HRIS owner exports an approved effective-dated history extract to protected storage.
2. Operator passes its path with `--hris-history-path`.
3. `load_governed_hris_history` validates canonical bitemporal columns, source lineage, immutable source record IDs, one source system, one extraction timestamp, provenance marker, and temporal overlap rules.
4. The validated history replaces only the history frame on the Gold input object; employee-month membership, hire dates, and exit outcomes continue to come from the existing Gold tables.
5. Feature engineering resolves attributes valid and known at each snapshot and constructs the existing 90-day forward attrition label.
6. Production-mode feature output is written only to an absolute path outside the Git repository. The script prints aggregate counts, not employee-level rows.

## Run locally with synthetic demo data

From `ai-service`:

```bash
python scripts/generate_synthetic_employee_history.py
python scripts/build_attrition_features.py --horizon-days 90
```

The default mode remains synthetic demo and must not be represented as production model training data.

## Run with an approved HRIS extract

From `ai-service`, after mounting the approved extract and approved output storage:

```bash
python scripts/build_attrition_features.py \
  --sample-data-dir /secure/gold-equivalent-csv-export \
  --hris-history-path /secure/hris/hris_employee_history.csv \
  --as-of 2026-09-30 \
  --horizon-days 90 \
  --output /secure/ai-artifacts/attrition_training_dataset.csv
```

Governed HRIS mode also requires `--sample-data-dir` to point to an absolute protected directory containing the approved Gold-equivalent CSV inputs (employees, departments, exits, ATS candidates, and requisitions). It rejects repository/sample-data inputs, so production history cannot accidentally be combined with the repository's synthetic employee/exit tables. It also rejects an output path that is relative or resolves inside this Git repository. The secure mounts, encryption, access controls, retention, and audit logging must be provided by the deployment environment.

## Source boundary and reconciliation

The adapter proves that the extract conforms structurally to the contract; it does not independently prove that the source system or provenance marker is authentic. Before training, the HRIS/data owner must attest to:

- the authoritative source entity and source-system identity;
- whether records are event history or reconstructed snapshots;
- valid-time and system-time meanings, timezone, corrections, deletions, and late-arriving updates;
- mapping from HRIS organization codes to Gold dimension keys;
- stable pseudonymous employee keys shared with Gold employee and exit tables;
- extraction cutoff, row counts, source freshness, and reconciliation totals;
- privacy, security, retention, and model-use approval.

The employee key used in the history must match the employee key used by the Gold membership and exit data. A mismatch or missing point-in-time history is a hard failure; the pipeline must not substitute current-state attributes.

## What remains outside this phase

- Direct API/connector access to a named HRIS.
- Fabric Lakehouse / Delta read implementation and managed identity.
- Source-specific schema discovery and mapping.
- Independent provenance attestation and production reconciliation.
- Model training, evaluation, deployment, and inference.

These require the actual provider, approved source location, owner, schema, and credentials/identity mechanism. Never place employee extracts, credentials, or tokens in Git.
