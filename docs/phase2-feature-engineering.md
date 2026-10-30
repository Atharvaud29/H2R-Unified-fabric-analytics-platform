# Phase 2 — AI Feature Engineering & Dataset Preparation

**Status:** Initial implementation  
**Scope:** Workforce attrition training-data preparation from the existing Gold-equivalent service layer  
**Non-goal:** This increment does not train, register, or serve a predictive model.

## Architecture

The Phase 2 local path reuses the existing transformations and data contract:

    sample-data CSVs → load_gold() → GoldTables → build_attrition_dataset() → training CSV

The Fabric target remains:

    Gold Delta tables → equivalent feature transformation in Fabric → governed feature/training dataset

The local pandas implementation is a reproducible development path, not a claim that the AI service is already connected to Fabric.

## Initial prediction target

- Entity grain: employee × month-end snapshot
- Target: exit_within_horizon
- Positive class: a last-working-date event for the employee in (snapshot_date, snapshot_date + horizon_days]
- Default horizon: 90 calendar days
- Eligible rows: employee is active at the snapshot and the full forward horizon is observable on or before the dataset as_of cutoff
- Censoring: snapshots without a fully observed forward horizon are excluded, not labelled negative

## Model input contract

| Feature | Type | Meaning |
|---|---|---|
| department_id | categorical | Department from the available employee record |
| location_id | categorical | Location from the available employee record |
| grade_id | categorical | Job grade from the available employee record |
| employment_type | categorical | Employment type |
| work_mode | categorical | Work arrangement |
| tenure_months | integer | Completed tenure months at the snapshot |
| hire_month | integer | Calendar month of hire |
| snapshot_month | integer | Calendar month of the snapshot |
| snapshot_quarter | integer | Calendar quarter of the snapshot |

The dataset also contains employee_id and snapshot_date as traceability metadata and exit_within_horizon as the target. Metadata columns must not be passed to model fitting.

## Excluded from model inputs

The first feature contract intentionally excludes employee name, email, employee ID, manager ID, gender, date of birth, age/age band, termination date, exit reason, exit interview information, and any field that directly reveals a future outcome.

This is a conservative starting point, not a complete fairness assessment. Before any employment-impacting use, the model requires documented purpose limitation, access controls, subgroup/fairness evaluation, human review, and legal/privacy review. Predictions must not be used as the sole basis for decisions about an individual.

## Important data limitations

1. Current source files provide current employee attributes, not a complete historical slowly-changing employee dimension. Department, location, grade, employment type, and work mode are therefore treated as the available record's values for each historical snapshot. This may introduce historical feature drift; use effective-dated Gold history before production training.
2. The current GoldTables adapter includes workforce, recruitment, and exit frames only. Leave, attendance, payroll, performance, onboarding, and learning features are not added until their Gold-equivalent adapters and point-in-time semantics are implemented.
3. Synthetic sample data is useful for pipeline validation only. It is not evidence of real-world model performance or valid employment-risk estimates.
4. The 90-day horizon is an initial versioned default and should be reviewed with the business owner before model training.

## Build locally

From the ai-service directory:

    pip install -r requirements.txt
    pytest
    python scripts/build_attrition_features.py --horizon-days 90

Optional arguments:

    python scripts/build_attrition_features.py \
      --as-of 2026-06-30 \
      --sample-data-dir ../sample-data \
      --horizon-days 90 \
      --output artifacts/attrition_training_dataset.csv

The output CSV is a generated artifact and should not be committed with employee-level rows. The script prints aggregate counts only.

## Acceptance criteria for this increment

- Feature rows are built only from existing Gold-equivalent frames.
- The label uses a forward event window and fully observed horizons.
- Future termination fields and protected attributes are not model inputs.
- Employee IDs remain metadata only.
- Tests cover label boundaries, active-at-snapshot filtering, censoring, and excluded fields.
- The implementation remains separate from model training and prediction serving.
