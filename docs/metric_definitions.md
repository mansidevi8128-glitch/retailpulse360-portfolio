# Metric Definitions

> RetailPulse 360 is fictional and all data is synthetic. The definitions below were derived from checks against the data itself (see `reports/data_quality_report.md` §4) and are implemented once in `src/retailpulse360/metrics.py`, mirrored in the SQL scripts, and verified by tests.

## How order status drives the money fields

| Order status | `net_revenue_usd` | `total_cost_usd` | `profit_usd` | Counted in |
|---|---|---|---|---|
| Completed | GMV + shipping fee | merchandise cost | revenue − cost | revenue, AOV, profit, refund-rate denominator |
| Refunded | 0 | merchandise cost (goods not recovered) | − cost (a loss) | profit (as a loss), refund rate |
| Cancelled | 0 | 0 | 0 | GMV, cancellation rate only |

Sales tax (`tax_amount_usd`) is a pass-through liability and is excluded from every revenue measure.

## Sales and profitability

| Metric | Formula | Grain / notes |
|---|---|---|
| **GMV** (gross merchandise value) | Σ `gross_merchandise_value_usd` over **all placed orders** | Post-discount merchandise value; excludes shipping and tax. A demand measure. It is *not* pre-discount, despite the name. |
| **Net revenue** | Σ `net_revenue_usd` | Non-zero only for Completed orders; = merchandise after discounts + shipping fee. |
| **Shipping revenue** | Σ `shipping_fee_usd` on Completed orders | Included in net revenue; no shipping *cost* exists in the data. |
| **Product-level profit** | Σ `profit_usd` = net revenue − merchandise cost | Includes refund losses. Excludes shipping, fulfilment, payment, support, overhead and marketing costs, so it is a contribution measure, **not net income**. |
| **Profit margin %** | profit ÷ net revenue × 100 | |
| **Refund loss** | − Σ `profit_usd` on Refunded orders | Merchandise cost written off. |
| **Category revenue / profit** | Σ `line_revenue_usd` on Completed lines; profit = revenue − cost of Completed and Refunded lines | Line-item grain. Excludes shipping, so categories sum to net revenue − shipping revenue. |
| **Gross margin % (category)** | category profit ÷ category revenue | |

## Orders and customers

| Metric | Formula | Notes |
|---|---|---|
| **Orders placed** | count of all orders | any status |
| **Completed orders** | count where status = Completed | |
| **AOV** | net revenue ÷ completed orders | Refunded and cancelled orders are excluded from both numerator and denominator. |
| **Refund rate %** | refunded ÷ (completed + refunded) × 100 | Share of *fulfilled* orders that were refunded. Cancelled orders were never fulfilled. |
| **Cancellation rate %** | cancelled ÷ orders placed × 100 | |
| **Purchasing (active) customers** | distinct customers with ≥ 1 completed order in the period | |
| **Revenue per customer** | net revenue ÷ all customers in the group | Includes customers who never bought, so groups of different maturity are comparable. |
| **Repeat-purchase rate %** | purchasing customers with ≥ 2 completed orders ÷ purchasing customers | |
| **MoM growth %** | (this month ÷ previous month − 1) × 100 | All months are complete (data runs through 2026-05-31). |
| **Like-for-like YoY** | Jan–May of each year | 2026 has only 5 months, so full years are never compared to a partial year. |

## Retention and RFM

| Metric | Definition |
|---|---|
| **Cohort** | Month of a customer's first *observed* completed order. Orders start in Jan 2024, so 2024 cohorts include earlier sign-ups (left-censored). |
| **Retention (month N)** | Share of a cohort with ≥ 1 completed order N calendar months after the cohort month. Cells not yet observable are blank. |
| **Average retention curve** | Customer-weighted average across cohorts observable at month N. |
| **Recency (RFM)** | Days from last completed order to 2026-05-31; never-buyers use days since sign-up. |
| **Frequency / Monetary (RFM)** | Completed orders / net revenue over all observed history. |
| **R, F, M scores** | Quintiles (1–5, 5 = best) among purchasing customers; never-buyers score 1. |

## Marketing

| Metric | Formula | Notes |
|---|---|---|
| **CTR %** | clicks ÷ impressions × 100 | |
| **CPC** | spend ÷ clicks | |
| **Click-to-lead %** | leads ÷ clicks × 100 | |
| **Cost per lead (CPL)** | spend ÷ leads | |
| **Spend per new customer** | channel spend ÷ customers whose `acquisition_channel` is that channel and who signed up in the same period | Attribution-based ratio, not incremental CAC. |
| **First-year value per customer** | mean net revenue / profit in the 365 days after sign-up | Only customers who signed up 2024-01-01 to 2025-05-31, so every customer has a full, observed year. |
| **Spend-to-first-year-profit ratio** | spend per new customer ÷ first-year profit per customer | > 1 means acquisition cost is not recovered within a year (before other costs). |

Marketing data is at month × channel grain and has no customer key, so it is never joined row-by-row to orders.

## Web funnel and support

| Metric | Formula |
|---|---|
| **Session conversion rate %** | sessions with `converted = 1` ÷ sessions |
| **Cart rate %** | sessions with ≥ 1 cart add ÷ sessions |
| **Checkout completion %** | converted ÷ checkout started |
| **Tickets per 100 orders** | tickets opened in month ÷ fulfilled (completed + refunded) orders in month × 100 |
| **Satisfied %** | tickets with CSAT ≥ 4 ÷ tickets |
| **Resolution time** | `resolution_hours` (mean and median reported; distribution is right-skewed) |

## Model metrics

| Metric | Meaning |
|---|---|
| **ROC-AUC** | Probability that a random churner gets a higher score than a random non-churner (0.5 = random). |
| **PR-AUC (average precision)** | Precision averaged over recall levels; a random model scores the base rate (~0.27). |
| **Precision** | Of customers flagged, the share who actually churned. |
| **Recall** | Of customers who churned, the share who were flagged. |
| **F1** | Harmonic mean of precision and recall. |
| **Brier score** | Mean squared error of predicted probabilities (lower is better). |
| **Lift** | Precision among the top X% ÷ base rate. |
| **Silhouette** | Cluster separation from −1 to 1; about 0.2–0.25 indicates weak-to-moderate structure. |
| **Adjusted Rand index** | Agreement between two clusterings (1 = identical); used for stability checks. |
