# SQL Analysis Questions

The original 15 analysis questions and the script that answers each one. All scripts target PostgreSQL and were executed on PostgreSQL 16 (see `docs/sql_data_loading_guide.md`).

| # | Question | Script |
|---|---|---|
| 1 | Validate row counts, primary-key uniqueness and missing values. | `02_load_data.sql`, `03_data_quality_checks.sql` |
| 2 | Calculate monthly revenue, profit, orders, customers and AOV. | `04_monthly_kpis.sql` |
| 3 | Calculate month-over-month revenue and profit growth. | `04_monthly_kpis.sql` |
| 4 | Rank product categories by revenue, profit and gross margin. | `05_product_category_profitability.sql` |
| 5 | Compare regions by customers, revenue, AOV and refund rate. | `06_regional_analysis.sql` |
| 6 | Compare acquisition channels by customer count and 12-month customer value. | `07_acquisition_channel_performance.sql` |
| 7 | Find repeat-purchase rate and purchase-frequency distribution. | `08_repeat_purchase_frequency.sql` |
| 8 | Calculate refund rate by category, channel and month. | `09_refund_analysis.sql` |
| 9 | Analyze support tickets, resolution time and CSAT. | `10_support_csat.sql` |
| 10 | Build RFM metrics at customer level. | `11_rfm.sql` |
| 11 | Create monthly cohorts and retention rates. | `12_cohort_retention.sql` |
| 12 | Identify customers with high revenue but declining engagement. | `11_rfm.sql` ("At risk" group: high F/M, low R) |
| 13 | Compare website/mobile-app/marketplace performance. | `04_monthly_kpis.sql` (sales-channel comparison), `09_refund_analysis.sql` (refunds by sales channel) |
| 14 | Evaluate marketing channel spend, clicks, leads and cost per lead. | `13_marketing_efficiency.sql` |
| 15 | Produce a clean customer-level feature table for modeling. | `14_customer_features.sql` |
