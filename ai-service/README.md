# H2R AI Analytics Service (Phase 1)

Read-only FastAPI service that computes a small set of **workforce** and **recruitment** KPIs from the repository’s synthetic `sample-data/` CSVs. It does not call Fabric, Power BI, or an LLM.

Gold-equivalent frames are built in pandas using the same rules as `notebooks/02_silver_transformation.ipynb` and `notebooks/03_gold_dimensional_model.ipynb` (type casts, gender map, de-duplication, quarantine, monthly headcount snapshot, recruitment flags).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Process up; whether required CSVs are present |
| GET | `/kpis` | Catalog of supported KPI definitions, including documented DAX/SQL conflicts |
| GET | `/kpis/{name}` | Calculate one KPI |

Query parameters for `/kpis/{name}`:

- `as_of` — `YYYY-MM-DD`. Default is the maximum date found in the CSVs (not the machine clock).
- `period` — `all` (default for most period KPIs), `rolling_12m`, or `latest_month`. Snapshot KPIs (`active_employees`, `female_pct`, `avg_tenure_yrs`) ignore `period`.

Rates use **ratios** (DAX `DIVIDE`), not ×100. A zero denominator returns `value: null` and `denominator_zero: true`.

## Implemented KPIs

Workforce: `active_employees`, `headcount`, `hires`, `exits`, `net_headcount_change`, `average_headcount`, `attrition_pct`, `attrition_pct_rolling_12m`, `female_pct`, `avg_tenure_yrs`, `regrettable_exits`

Recruitment: `applicants`, `offers`, `candidates_hired`, `offer_acceptance_pct`, `applicant_to_hire_pct`, `avg_time_to_hire_days`, `avg_time_to_fill_days`

`attrition_pct` follows the data-dictionary / DAX formula (exits ÷ average monthly headcount). It does **not** use `vw_monthly_workforce_movement.monthly_attrition_pct` (that view divides by `COUNT(*)` for a single month). See `app/catalog/kpi_catalog.yaml`.

## Run locally

```bash
cd ai-service
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload --port 8000
```

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/kpis
curl "http://127.0.0.1:8000/kpis/attrition_pct?period=rolling_12m"
```

Optional: copy `.env.example` to `.env` and set `SAMPLE_DATA_DIR`.

Logs record KPI names, periods, and row counts only — not employee names, emails, or IDs.
