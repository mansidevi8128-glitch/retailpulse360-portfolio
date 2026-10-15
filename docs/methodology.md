# Methodology

> RetailPulse 360 is a fictional company and the data is synthetic (an AI-assisted learning and portfolio project). The methods are the real deliverable. The numbers show how they behave on simulated data.

## 1. Workflow

```
Raw CSVs (read-only) ─► Data-quality audit ─► KPI definitions ─► EDA + SQL analysis
                                   │                                      │
                                   └─► Snapshot rebuild / leakage audit ──┤
                                                                          ▼
                          Churn model (Notebook 02)   Segmentation (Notebook 03)
                                          └──────────────┬──────────────┘
                                                         ▼
                         Reports (generated) · Dashboard · Recommendations
```

Every number in the reports is produced by code (`scripts/run_pipeline.py`), and the same functions are used by the notebooks, the dashboard and the tests.

## 2. Data-quality audit

- **Structure:** row and column counts against the documentation, data types, date ranges, missing values and exact duplicate rows.
- **Keys:** primary-key uniqueness, including the composite key `month + channel` for marketing; foreign-key orphans for five relationships; orders without items. Repeated foreign keys, such as many orders per customer, are expected and are not counted as duplicates.
- **Financial reconciliation:** line items are aggregated to order grain first (so the join is one-to-one, with no fan-out). The order fields are then tested by status. All eight rules hold with zero violations, which settles the definitions in `docs/metric_definitions.md`.
- **Business rules:** dates relative to sign-up and snapshot, value ranges, funnel consistency, marketing funnel consistency. Two findings are kept and explained: coupon flags without a discount, and two loss-making deeply discounted orders.
- **Outliers:** counted with a 3 × IQR rule and kept (plausible values; raw data is never altered).
- **Snapshot audit:** every snapshot feature was rebuilt from raw events on or before the snapshot date, with a 100% match. This found a recency sentinel and imputed CSAT values. Corrections are added as new columns; the source is not overwritten.

## 3. KPI design choices

| Decision | Reason |
|---|---|
| AOV uses completed orders only | Refunded and cancelled orders have zero revenue and would understate AOV. |
| Refund rate denominator = completed + refunded | Cancelled orders were never fulfilled, so they cannot be refunded. |
| Profit includes refund losses | That is how the source data records it, and it is economically correct (goods not recovered). |
| Like-for-like Jan–May year comparison | 2026 has only five months of data. |
| First-year value window for channels | Lifetime totals favour channels that acquired customers earlier. |
| Marketing never joined row-level to orders | No shared key; a join would duplicate spend. |
| Significance tests for rate gaps | Chi-square tests stop small gaps (e.g. marketplace refunds, p ≈ 0.07) from being over-read. |

## 4. SQL layer

PostgreSQL scripts mirror the Python logic. CTEs aggregate at the correct grain before any join, window functions (`LAG`, `NTILE`, `RANK`, `ROW_NUMBER`, `SUM() OVER`) handle growth, ranking and RFM, and views (`monthly_kpis_v`, `line_financials_v`, `first_year_value_v`, `customer_rfm_v`, `cohort_retention_v`, `customer_features_v`) make results reusable. Constraints (PK, FK, CHECK) validate the data during loading. The SQL was executed on PostgreSQL 16, and its results are compared with the pandas results by automated tests.

## 5. Churn prediction

1. **Target and baselines:** 26.7% churn. Accuracy is rejected as the main metric because always predicting "no churn" scores 73%.
2. **Leakage review:** time-window rebuild; ID and target guard; single-feature AUCs (max ≈ 0.77, so no leaked label); the recency sentinel is replaced by true recency plus flags.
3. **Split:** stratified 75/25 with a fixed seed. The test set is used once.
4. **Pipelines:** `ColumnTransformer` (StandardScaler for Logistic Regression, passthrough for trees, plus OneHotEncoder) inside `Pipeline`, so preprocessing is fitted only on training folds.
5. **Models:** Logistic Regression (baseline), Random Forest and Histogram Gradient Boosting, compared with 5-fold stratified CV on ROC-AUC and PR-AUC.
6. **Selection rule:** best CV PR-AUC; prefer Logistic Regression if within 0.01 of the best.
7. **Threshold:** maximise F1 on out-of-fold training predictions, never on the test set. A capacity table translates scores into outreach volumes, with capacity explicitly labelled as an assumption.
8. **Interpretation:** permutation importance on the test set (robust to correlated features), plus standardised coefficients.
9. **Error analysis and calibration:** profiles of false negatives and false positives; observed against predicted churn by score decile.
10. **Sensitivity check:** the model trained on the sentinel recency performs about the same, so it does not depend on the artifact.
11. **Customer scores:** out-of-fold predictions for all 6,000 customers, so no customer is scored by a model that saw their label. These feed the dashboard.

## 6. Segmentation

1. **Features (8):** recency, frequency, monetary value, gross margin %, discount %, refund rate, 90-day web sessions and 12-month support tickets. Highly correlated value measures (profit, AOV, category diversity) are used only for profiling.
2. **Transform:** `log1p` on skewed counts and amounts, then standardisation.
3. **Choose k:** inertia and silhouette for k = 2…8. The rule is the highest silhouette with k ≥ 3 and every cluster ≥ 5% of customers, which gives k = 4. k = 2 is rejected because it only separates customers without recent purchases.
4. **Stability:** adjusted Rand index across five seeds (≈ 1.0) and ten bootstrap refits (mean ≈ 0.85).
5. **Profiling and naming:** cluster means indexed to the customer average; names assigned by ordered, written rules (`segmentation.name_segments`).
6. **Post-hoc description:** churn rate and loyalty mix per segment. The target is never a clustering input (test-enforced).
7. **Action playbook:** one action per segment, each framed as a hypothesis to test, with metrics to monitor.

## 7. Recommendations framework

Each recommendation in `reports/business_recommendations.md` states the observed evidence, the implication, a testable action and the metrics to monitor. Priority reflects the size of the effect and how directly the data supports the action. No revenue uplift, savings or ROI is claimed, because the data contains no experiment results.

## 8. Reproducibility

- Fixed random seed (`RANDOM_STATE = 42`) for splits, models, K-Means and bootstraps.
- Paths are relative to the repository root (`config.PROJECT_ROOT`).
- One command regenerates every output: `python scripts/run_pipeline.py`.
- Tests cover definitions, safeguards, the SQL and pandas match, and the dashboard. CI runs them on every push.
