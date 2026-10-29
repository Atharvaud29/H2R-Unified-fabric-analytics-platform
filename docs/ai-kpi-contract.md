# AI Service KPI Contract — Phase 1

**Status:** Draft for validation  
**Scope:** The 17 KPIs currently exposed by `ai-service`  
**Purpose:** Record the current metric contract and known differences before changing calculations. This document does not change runtime behavior.

## Contract rules

1. The KPI catalog (`ai-service/app/catalog/kpi_catalog.yaml`) is the service's declared metadata contract.
2. The Python KPI engine is the current executable implementation for the CSV-backed service; it is not yet a live Fabric Gold adapter.
3. Power BI DAX and Fabric SQL are comparison references, not automatically interchangeable formulas. Filter context, date grain, grouping and units must be aligned before comparing values.
4. Rate values returned by the API are fractions/ratios (for example, `0.25` means 25%), unless the API contract is deliberately changed later.
5. Undefined rates must remain null when their denominator is zero; they must not silently become zero.
6. Changes to formulas require regression tests with fixed inputs and expected numerator, denominator, value, period and unit.

## Current KPI coverage

| Area | KPIs exposed by the current service |
|---|---|
| Workforce | Active Employees, Headcount, Hires, Exits, Net Headcount Change, Average Headcount, Attrition %, Attrition % (Rolling 12M), Female %, Avg Tenure (Yrs), Regrettable Exits |
| Recruitment | Applicants, Offers, Candidates Hired, Offer Acceptance %, Applicant to Hire %, Avg Time to Hire (Days), Avg Time to Fill (Days) |

This is the current AI-service scope, not the full set of measures in the Power BI model.

## Known reconciliation items

| KPI / topic | Current Python/API behavior | DAX / SQL / dictionary reference | Action before changing code |
|---|---|---|---|
| Attrition % | Exits divided by average monthly headcount; API returns a ratio, not percent points. | Data dictionary uses exits ÷ average monthly headcount. DAX uses `DIVIDE([Exits], [Average Headcount])`. One SQL reporting view calculates a single-month exits ÷ row count × 100; another query groups by fiscal year and multiplies by 100. | Treat dictionary + DAX as the likely business definition, but confirm expected reporting grain and API unit. Keep SQL comparisons at matching grain and normalize units. |
| Rolling 12-month attrition | Exits divided by average headcount over 12 calendar month-ends through the `as_of` month. | DAX uses `DATESINPERIOD` over `dim_date`; date-table coverage and filter context may affect the included months. | Test exact month boundaries, incomplete history and `as_of` dates against the intended date-table semantics. |
| Average Headcount | Mean of monthly distinct employee counts for months present in the local snapshot. | DAX iterates `VALUES(dim_date[month_start])`; SQL KPI query averages grouped monthly headcount. | Decide how months with no snapshot rows are handled and align all comparisons to the same month set. |
| Hires / Exits | Counts distinct employees flagged in the monthly headcount snapshot for the selected API period. | DAX is filter-context-sensitive; SQL views may aggregate by month. Exit facts can differ from monthly snapshot flags. | Validate period filters and event-date treatment with fixed fixtures. |
| Headcount / Active Employees | Headcount uses the latest available month-end on or before `as_of`; Active Employees uses the current active flag in the CSV-derived employee frame. | DAX depends on the Direct Lake date table and model filters. | Confirm intended snapshot date and filters when comparing API with Power BI. |
| Offer Acceptance % | Hired ÷ Offered; offered means stage order >= Offered, including Hired candidates. Result is a ratio. | DAX uses Candidates Hired ÷ Offers; dictionary uses Hired ÷ Offered. | Preserve the funnel definition and test denominator membership, duplicates and zero offers. |
| Time to Hire / Time to Fill | Mean of non-null durations; negative time-to-hire values are excluded and reported as data-quality notes. Durations require a candidate-to-employee link. | DAX `AVERAGE` skips blanks; dictionary defines the date subtraction. | Test null links, negative durations, and exact date differences; document exclusions. |
| Tenure | CSV implementation uses a pandas approximation of Spark `months_between` and local `as_of`. | Silver notebook uses Spark `months_between`; source logic may use current date when no termination date exists. | Compare rounding and date semantics with controlled dates before claiming exact parity. |
| Recruitment periods | Recruitment KPIs currently use all available recruitment rows; period filters do not provide date-scoped recruitment analysis. | Power BI can apply date-table/report filter context. | Keep this limitation explicit; add date filtering only with an agreed event-date rule. |
| Coverage | The service currently exposes 17 workforce/recruitment KPIs. | DAX model also includes learning, leave, performance, compensation, time-intelligence and data-health measures. | Do not imply these additional domains are supported by the assistant until their data adapter and KPI definitions are implemented and tested. |

## Regression-test requirements

Before changing a KPI implementation, add tests that assert:

- numerator and denominator, not just the final value;
- ratio units and null behavior for a zero denominator;
- `all`, `latest_month` and `rolling_12m` boundaries where supported;
- behavior with empty data, missing values and duplicate identifiers;
- date handling and source grain;
- catalog metadata and returned API payload agree.

## Exit criteria for KPI reconciliation

- Each in-scope KPI has one approved business definition, unit, grain, date basis and default period.
- Any intentional API-vs-DAX differences are documented with examples.
- SQL comparisons use the same period, filters and unit as the API result.
- Regression tests pass before formula changes are merged.
- No unsupported KPI is silently presented as available.
