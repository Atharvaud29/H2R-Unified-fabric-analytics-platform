# AI KPI Reconciliation Matrix

**Status:** Working draft — implementation reference  
**Branch:** `ai/phase1-baseline-kpi-contract`  
**Rule:** This matrix records current behavior and proposed alignment. It does not authorize or perform production formula changes.

## Canonical comparison rules

- Compare identical reporting windows, date filters, row grain and employee/candidate population.
- Normalize percentages before comparing: Python API ratios (0–1) are equivalent to percent-point outputs multiplied by 100.
- Distinguish employee-month snapshot flags from event-level exit facts.
- Treat empty or zero-denominator rates as undefined (`null`) in the AI API unless the business contract explicitly says otherwise.
- Do not claim live Fabric parity until the service reads the Gold tables and the same fixture/query is run against both implementations.

## Priority reconciliation matrix

| Priority | KPI / behavior | Python service (current) | DAX / SQL / dictionary evidence | Proposed contract | Regression test needed | Decision/status |
|---|---|---|---|---|---|---|
| P0 | Attrition % | Exits flagged in filtered monthly snapshot ÷ mean monthly distinct employee count; returns ratio. | Dictionary: exits ÷ average monthly headcount. DAX: `DIVIDE([Exits], [Average Headcount])`. SQL monthly view: exits ÷ `COUNT(*)` × 100, which is a different denominator and unit. | Use exits ÷ average monthly headcount; API unit remains ratio. Validate matching month set and numerator. | A controlled 2–3 month fixture with known monthly headcounts/exits; assert numerator, denominator, ratio and zero-denominator behavior. | Definition likely aligned to dictionary/DAX; verify month population before code changes. |
| P0 | Rolling 12M attrition | Uses 12 month-end dates ending in `as_of` month; computes flagged exits ÷ mean monthly headcount in filtered snapshot. | DAX uses `DATESINPERIOD(dim_date[date], _end, -12, MONTH)`; exact boundaries depend on date table and filter context. | Define calendar-month interpretation explicitly as the 12 month-ends ending in `as_of` month. | Test exit in month before window, first and last included month, missing month snapshot, and mid-month `as_of`. | Python behavior needs comparison against intended DAX date-table semantics. |
| P0 | Average Headcount | Mean of monthly distinct employee IDs for month-end groups present in the filtered dataframe. | DAX iterates all `VALUES(dim_date[month_start])`; SQL groups only month-end records present. | Define whether months with no fact rows are excluded or counted as zero. Recommended: use the model's explicit date/month spine and a documented missing-snapshot policy. | Fixture with a missing month and an explicit expected month set. | Business/model decision required. |
| P0 | Hires / Exits | Distinct employees with `is_new_hire` / `is_exit` flags in the headcount snapshot. | DAX counts distinct flagged employee IDs in the same fact; exit analysis also uses event-level `fact_exit`. | For monthly movement KPIs, use snapshot flags; for exit-reason/voluntary/regrettable analysis, use event-level exit facts. Do not mix them without naming the metric. | Duplicate employee-month rows, same employee in multiple months, exit event vs snapshot flag. | Clarify the grain for each KPI; current approach may be appropriate for movement. |
| P1 | Headcount vs Active Employees | Headcount uses month-end active snapshot at `as_of`; active employees uses current `is_active` flag from employee dimension. | DAX uses fact snapshot for Headcount and dimension current-state flag for Active Employees. | Keep them distinct: period-end snapshot vs current employment status. | Employee terminates mid-month; `as_of` before/after termination. | Semantics are intentionally different; document in assistant answers. |
| P1 | Offer Acceptance % | Hired count ÷ offered count; offered flag is true for candidates at Offered or later stage, including Hired. Returns ratio. | DAX uses Candidates Hired ÷ Offers; dictionary says Hired ÷ Offered. | Keep hired ÷ offered, but denominator must be the number of candidates who reached offer, counting each candidate once. | Stages Applied/Offered/Hired, duplicates, zero offers; assert denominator membership. | Formula aligns conceptually; verify `is_offered` creation and candidate grain. |
| P1 | Applicant to Hire % | Hired candidates ÷ all rows in recruitment frame. | DAX uses Candidates Hired ÷ Applicants. | One row per candidate application; if candidates can apply more than once, name and define whether denominator is applications or unique candidates. | Duplicate candidate IDs and null IDs. | Source grain decision required. |
| P1 | Time to Hire | Mean of non-null, non-negative `time_to_hire_days`; negative values excluded with a note. | DAX `AVERAGE` ignores blanks but does not inherently exclude negative values. Dictionary defines hire date minus application date. | Exclude invalid negative durations from the KPI and expose excluded count as data-quality evidence; confirm this business rule. | Valid, null, negative durations and date arithmetic. | Intentional difference from plain DAX average must be approved/documented. |
| P1 | Time to Fill | Mean of non-null `time_to_fill_days`; nulls excluded. | DAX `AVERAGE` ignores blanks; dictionary uses hire date minus requisition open date. | Mean only for records with valid requisition-open and hire dates and a reliable candidate-to-requisition/employee link. | Missing link, null dates, exact day boundary. | Confirm candidate/requisition linkage and population. |
| P1 | Avg Tenure (Yrs) | Mean of active employees' tenure years from pandas approximation of Spark `months_between`, rounded per Silver transform. | DAX averages `dim_employee[tenure_years]` for active employees; notebook uses Spark semantics. | Match Silver notebook's calculation and rounding; use the same `as_of` date. | End-of-month dates, leap year, hire date on 29th/30th/31st, fixed `as_of`. | Verify parity before adjusting implementation. |
| P2 | Recruitment time filters | Recruitment KPIs currently use all available recruitment rows, regardless of requested workforce period. | DAX report can be filtered by date dimension; correct relationship and event date matter. | Do not pretend recruitment KPIs support period filtering until an event-date contract is implemented (applied date for applicants, offer date for offers, hire date for hires/time-to-hire). | Requests with explicit dates; verify each KPI uses its agreed event date. | Known limitation; schedule after core NL assistant has a stable data contract. |
| P2 | API rate representation | API outputs ratio values (e.g. 0.25); catalog unit is `ratio`. | DAX/SQL display may format as percent or multiply by 100. | Keep API machine value as ratio and format as percent only in presentation. | API payload asserts unit and value; presentation formatting test. | Recommended contract; do not multiply API value by 100. |

## Implementation sequence

1. Approve the P0 definitions and the missing-month policy.
2. Add/adjust focused regression tests for those definitions.
3. Compare test fixture outputs to the local KPI engine.
4. Only then change calculation code if a proven mismatch exists.
5. Add a Fabric comparison run after a supported Gold data adapter and environment are available.
6. Use the approved contract to ground natural-language answers with metric, period, unit, filters and evidence.

## Explicit non-goals for this step

- No production KPI formulas changed.
- No live Fabric or Power BI queries executed.
- No predictive or anomaly-detection logic added.
- No unsupported KPI or data source advertised as available.
