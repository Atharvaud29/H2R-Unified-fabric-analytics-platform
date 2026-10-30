# Phase 3.1.1 – Historical Employee Data Source Integration

## Objective

Connect the bitemporal employee-history contract to the local Gold-equivalent adapter and the attrition feature builder. A feature row must use the employee attributes valid and known at its snapshot date. The feature builder must not silently fall back to the current employee dimension.

## Demo source and provenance

The repository's current HRIS sample file contains one current-state employee row per employee; it does not contain observed historical attribute changes. This phase therefore adds a deterministic generator that creates **synthetic demonstration history** from the current sample rows.

- Output: \`sample-data/hris_employee_history_synthetic.csv\`
- Provenance: every row contains \`source_type=synthetic_demo\`.
- Previous attribute states and transition dates are fabricated deterministically for repeatable integration tests.
- The current-state attribute values anchor the latest generated state only.
- This file is not an HRIS event log, not evidence of actual employee movements, and not suitable for real employee risk decisions or claims of predictive validity.

## Source schema

The generator writes the bitemporal columns defined in Phase 3.1:

- \`employee_id\`
- \`effective_start_date\` inclusive
- \`effective_end_date\` exclusive; blank means open
- \`recorded_at\` UTC timestamp
- \`superseded_at\` UTC timestamp; blank means current system version
- \`department_id\`, \`location_id\`, \`grade_id\`, \`employment_type\`, \`work_mode\`
- \`source_type\` provenance marker

## Generate and validate

Run from \`ai-service\`:

\`\`\`bash
python scripts/generate_synthetic_employee_history.py
\`\`\`

Optional cutoff/output:

\`\`\`bash
python scripts/generate_synthetic_employee_history.py --as-of 2026-03-15 --output ../sample-data/hris_employee_history_synthetic.csv
\`\`\`

The generator validates interval integrity and prints aggregate row/employee/conflict counts only.

## Integration

\`load_gold()\` loads the optional history file when present, verifies the synthetic provenance marker, and runs bitemporal validation. The resulting \`GoldTables.employee_history\` is passed to the attrition feature builder.

\`build_attrition_dataset()\` now resolves all employee categorical features through \`point_in_time_employee_attributes()\` at each employee-month snapshot. Missing or ambiguous history is an error. There is no current-state fallback.

Generate the source before building features:

\`\`\`bash
python scripts/generate_synthetic_employee_history.py
python scripts/build_attrition_features.py --horizon-days 90
\`\`\`

## Acceptance criteria

- Deterministic output for identical input and cutoff.
- All generated rows explicitly labelled \`synthetic_demo\`.
- No overlapping bitemporal versions.
- Historical feature joins use valid time and system/knowledge time.
- Missing or ambiguous employee history fails closed.
- Attrition model input columns remain unchanged; employee ID remains metadata only.
- Full AI service tests pass.

## Production handoff

Replace the synthetic CSV with an approved HRIS change-event or effective-dated dimension feed. Preserve the same contract and provenance controls. Do not promote synthetic history to a production feature source. Before using real employee data, complete privacy/legal review, access controls, retention controls, fairness evaluation, and human oversight requirements.
