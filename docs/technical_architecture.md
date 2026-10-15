# Technical Architecture

## Design goals

- **One source of truth for logic.** KPI definitions, features and models are written once in `src/retailpulse360/`. The notebooks, the report pipeline, the dashboard and the tests all import them.
- **Raw data is immutable.** Loaders only parse types in memory. Derived columns are added in memory or written under `reports/`.
- **Everything is reproducible from one command.** `python scripts/run_pipeline.py` regenerates all reports, tables, figures and the README findings block.
- **Keep it simple.** A small package of plain functions, with no framework, database server or orchestration tool required for the Python path.

## Components

```
                         data/raw/*.csv  data/processed/customer_modeling_snapshot.csv
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
     src/retailpulse360 (Python)            sql/ (PostgreSQL)
     ├─ config.py      paths, constants      01 schema + constraints
     ├─ data.py        loaders               02 \copy load
     ├─ quality.py     audit checks          03 data-quality checks
     ├─ metrics.py     KPI definitions       04–13 business analysis
     ├─ features.py    snapshot rebuild,     14 customer feature view
     │                 leakage guard
     ├─ modeling.py    churn pipelines,
     │                 evaluation helpers
     ├─ segmentation.py K-Means workflow
     ├─ plotting.py    chart style/helpers
     ├─ reporting.py   Markdown rendering
     └─ pipeline.py    orchestration
                    │
     ┌──────────────┼───────────────────────┬──────────────────────┐
     ▼              ▼                       ▼                      ▼
 notebooks/   scripts/run_pipeline.py   dashboard/app.py        tests/
 (narrative)  → reports/*.md, *.json,   (Streamlit + Plotly;    (pytest; CI)
               tables/*.csv, figures/    reads raw data + the
               → README key findings     generated tables)
```

## Module responsibilities

| Module | Key functions |
|---|---|
| `config.py` | `PROJECT_ROOT`, data and report paths, `SNAPSHOT_DATE`, `RANDOM_STATE`, table and key metadata, colour palette, synthetic disclaimer |
| `data.py` | `load_raw_tables()`, `load_snapshot()` |
| `quality.py` | `table_overview`, `check_primary_keys`, `check_foreign_keys`, `reconcile_order_financials`, `business_rule_checks`, `outlier_summary`, `snapshot_reproduction_check` |
| `metrics.py` | `executive_summary`, `monthly_kpis`, `yearly_kpis`, `category_performance`, `customer_dimension_performance`, `marketing_efficiency`, `unit_economics_by_channel`, `session_funnel`, `support_summary`, `cohort_retention`, `rfm_table`, `two_proportion_test`, … |
| `features.py` | `build_customer_features` (rebuilds the snapshot), `add_corrected_features`, `assert_no_leakage`, feature lists |
| `modeling.py` | `build_models`, `cross_validate_models`, `classification_metrics`, `threshold_table`, `capacity_table`, `permutation_importance_table` |
| `segmentation.py` | `segment_matrix`, `evaluate_k`, `choose_k`, `fit_kmeans`, `stability`, `profile_segments`, `name_segments` |
| `reporting.py` | `render_data_quality_report`, `render_business_recommendations`, `render_key_findings`, `update_marked_section` |
| `pipeline.py` | `run_quality_audit`, `business_tables`, `run_churn_analysis`, `run_segmentation`, `customer_scores`, `statistical_checks` |

## Data flow for the churn model

1. `load_snapshot()` + `add_corrected_features()` → model frame (6,000 × 30).
2. `feature_matrix()` selects predictors and calls `assert_no_leakage()`.
3. `split_data()` → stratified 75/25 split.
4. `build_models()` → three `Pipeline`s (preprocessing + estimator).
5. `cross_validate_models()` on the training data only → `select_model()`.
6. Out-of-fold training predictions → `best_f1_threshold()`.
7. One evaluation on the test set → metrics, curves, capacity table and permutation importance.
8. `cross_val_predict` over all customers → out-of-fold scores in `reports/tables/customer_scores.csv` → dashboard.

## Dashboard

`dashboard/app.py` loads the raw tables once (`st.cache_data`), applies the sidebar filters to orders, tickets and marketing, and calls the same `metrics` functions. Ratios are therefore recomputed from filtered totals and never averaged. Model and segment views read the generated `reports/` files and are labelled as model-derived and synthetic. `tests/test_dashboard.py` runs the app headlessly with Streamlit's `AppTest`.

## Testing strategy

| Test file | What it protects |
|---|---|
| `test_data_quality.py` | row counts, key uniqueness, referential integrity, reconciliation rules, documented findings |
| `test_metrics.py` | KPI formulas on hand-checkable toy data, join fan-out, reconciliations on real data |
| `test_features.py` | 100% snapshot rebuild, future events cannot change features, sentinel and corrected recency, leakage guard |
| `test_modeling.py` | IDs and target excluded, stratified split, scaler fitted on training data only, metric helpers, selection rule |
| `test_segmentation.py` | target refused as a feature, scaling, k-selection rule, reproducibility, naming |
| `test_reporting.py` | Markdown helpers, generated reports free of TODOs and disclosing synthetic data, README block consistent with metrics |
| `test_sql_postgres.py` | runs all SQL on PostgreSQL and compares with pandas (skipped if no server) |
| `test_dashboard.py` | the app runs, shows real KPIs and responds to filters |

CI (`.github/workflows/tests.yml`) runs the full suite on Ubuntu with a PostgreSQL 16 service container.

## Dependencies

Only what the project uses: pandas, NumPy, scikit-learn, SciPy (via scikit-learn, used for chi-square tests), matplotlib, Plotly, Streamlit, Jupyter/nbconvert, psycopg2 and pytest. Versions are pinned in `requirements.txt` to the versions the project was tested with.
