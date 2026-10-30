# Phase 3.5 — HRIS / Fabric source connectivity foundation

## Objective

Create a provider-neutral boundary between an approved HRIS/Fabric source and
the existing governed-history / attrition feature pipeline. This phase does
not claim a live connection to Workday, SAP SuccessFactors, Darwinbox, or
Microsoft Fabric. No tenant, endpoint, workspace, lakehouse, table, or
credential has been configured.

## Implemented

- Extracted canonical DataFrame validation into
  `validate_governed_hris_history_frame`, shared by CSV and connector paths.
- Added `HrisHistoryConnector` protocol and immutable extraction context.
- Added a single validated read boundary that enforces source identity,
  extraction timestamp, canonical bitemporal history, lineage metadata and
  production source type before downstream use.
- Sanitizes provider exceptions so secrets, endpoint strings and query details
  are not copied into surfaced error messages.
- Added a connector validation CLI for a protected canonical extract and
  aggregate-only output.
- Added tests using a fake connector; tests do not require HRIS credentials,
  network access, or employee production data.

## Connector contract

A provider adapter implements:

```python
class HrisHistoryConnector(Protocol):
    def read_history(self, context: SourceReadContext) -> pd.DataFrame:
        ...
```

Returned data must include all `HISTORY_COLUMNS` from Phase 3.1 and
`source_system`, `source_record_id`, `extracted_at`, and
`source_type=hris_production`. Each extract must have one source system,
one timezone-aware extraction timestamp, unique source record IDs, and valid
bitemporal history.

The connector context pins the expected source system and extraction
timestamp. A mismatch is rejected before feature engineering. The optional
watermark is recorded as a presence flag only; provider-specific watermark
semantics and incremental extraction remain the provider adapter's
responsibility.

## Data flow

```text
Approved HRIS / Fabric source
        |
        v
Provider adapter (auth + query + pagination + watermark)
        |
        v
HrisHistoryConnector.read_history(context)
        |
        v
validate_connector_result()
        |
        +--> canonical bitemporal history
        +--> aggregate-only source report
        |
        v
Phase 3.4 governed history / feature ingestion
        |
        v
Point-in-time resolution -> leakage-aware attrition dataset
```

## Security and operations

- Use an approved secret store or managed identity in the deployment runtime;
  never put credentials, tokens, connection strings or private endpoints in Git.
- Grant read-only access and scope it to the required historical employee
  attributes and approved data domain.
- Keep source data and generated feature datasets in protected storage outside
  the repository.
- Use bounded extraction windows, explicit timeouts, pagination limits and
  retry/backoff in concrete adapters.
- Log run IDs, source identity, extraction timestamp, watermarks and aggregate
  counts only. Do not log employee IDs or row payloads.
- Treat `source_type=hris_production` as a contract marker, not independent
  proof of authenticity or business approval.
- Reconcile row counts, distinct employee coverage, effective-date coverage,
  late-arriving corrections, deleted/inactive records and source-to-Gold
  consistency before production training.

## Validation CLI

Run inside `ai-service` in an approved runtime:

```bash
python scripts/validate_hris_connector.py \
  --history-path /secure/hris/history.csv \
  --expected-source-system FABRIC_HR_LAKEHOUSE \
  --expected-extracted-at 2026-10-30T00:00:00Z
```

The CLI emits aggregate diagnostics only. Do not place real employee extracts
in the repository or CI artifacts.

## Not yet implemented / blocked on source decision

- Concrete Fabric Delta / OneLake reader or HRIS REST/OData/SQL adapter.
- Provider-specific field mapping into the canonical history contract.
- Managed identity / OAuth setup and tenant/workspace permissions.
- Incremental extraction, provider watermarks and replay/idempotency policy.
- Independent source attestation and production reconciliation thresholds.

These require the selected source, approved access path, schema/column mapping,
and data owner sign-off. Use anonymized schema samples only; do not share
employee records, tokens, passwords or connection strings.
