# SQL Data-Loading Guide (PostgreSQL)

The SQL scripts target **PostgreSQL 13 or later**. They were executed successfully on **PostgreSQL 16.15** while this project was built, and `tests/test_sql_postgres.py` re-runs them and compares the results with the Python implementation.

## Option A — one command (psql)

Prerequisites: PostgreSQL installed, and `psql` and `createdb` on your PATH.

```bash
cd retailpulse360-portfolio            # always run from the repository root
createdb retailpulse360
bash sql/run_all.sh retailpulse360     # schema → load → all analysis scripts
```

Each script's output is saved to `sql/output/<script>.txt` (git-ignored). Connection details come from the standard environment variables, for example:

```bash
export PGHOST=localhost PGPORT=5432 PGUSER=postgres PGPASSWORD=your_password
```

On Windows, run the same commands in Git Bash, or run the scripts one by one as shown in Option B.

## Option B — script by script

```bash
psql -d retailpulse360 -v ON_ERROR_STOP=1 -f sql/01_schema.sql      # creates schema "retailpulse"
psql -d retailpulse360 -v ON_ERROR_STOP=1 -f sql/02_load_data.sql   # loads CSVs, prints row counts
psql -d retailpulse360 -f sql/03_data_quality_checks.sql
psql -d retailpulse360 -f sql/04_monthly_kpis.sql
# ... continue in numeric order up to 14_customer_features.sql
```

`02_load_data.sql` uses psql's client-side `\copy` with **relative paths** (`data/raw/...`), so psql must be started from the repository root. Tables are loaded parent-first so that foreign keys are checked on insert.

Expected row counts printed by `02_load_data.sql`:

| table | rows |
|---|---:|
| customers | 6,000 |
| products | 120 |
| orders | 30,054 |
| order_items | 56,183 |
| web_sessions | 76,327 |
| support_tickets | 4,662 |
| marketing_spend | 174 |
| customer_modeling_snapshot | 6,000 |

## Option C — pgAdmin (no command line)

1. Create a database `retailpulse360`.
2. Open the Query Tool and run `sql/01_schema.sql`.
3. For each table in the `retailpulse` schema, right-click → **Import/Export Data** → Import, choose the matching CSV from `data/raw/` (or `data/processed/` for the snapshot), set Format = csv and Header = Yes. Import in this order: customers, products, orders, order_items, web_sessions, support_tickets, marketing_spend, customer_modeling_snapshot.
4. Run scripts `03`–`14` in the Query Tool. Each script starts with `SET search_path TO retailpulse;`.

## Script map

| Script | Purpose | Key techniques |
|---|---|---|
| `01_schema.sql` | tables, PK/FK, CHECK constraints, indexes | constraints as data validation |
| `02_load_data.sql` | load CSVs, verify row counts | `\copy`, `UNION ALL` |
| `03_data_quality_checks.sql` | uniqueness, nulls, orphans, date ranges, reconciliation, business rules | `LEFT JOIN … IS NULL`, `FILTER`, pre-aggregation |
| `04_monthly_kpis.sql` | monthly KPIs, MoM/YoY growth, Jan–May comparison | `DATE_TRUNC`, `LAG` over a named `WINDOW` |
| `05_product_category_profitability.sql` | category and product profit, ranking | line-grain view, `RANK`, `ROW_NUMBER` |
| `06_regional_analysis.sql` | regions and top states | separate CTEs per grain |
| `07_acquisition_channel_performance.sql` | lifetime and first-year value, unit economics | date-window joins |
| `08_repeat_purchase_frequency.sql` | frequency bands, repeat rate, days between orders | `LAG`, `PERCENTILE_CONT` |
| `09_refund_analysis.sql` | refunds by channel, discount, category, month | conditional aggregation |
| `10_support_csat.sql` | tickets, resolution, CSAT, load per order | `PERCENTILE_CONT`, CTE join |
| `11_rfm.sql` | RFM scores and groups | `NTILE(5)` |
| `12_cohort_retention.sql` | cohort matrix and weighted curve | `generate_series`, `make_interval` |
| `13_marketing_efficiency.sql` | CTR, CPC, CPL, spend vs profit by year | `SUM() OVER ()` shares |
| `14_customer_features.sql` | modeling feature view and snapshot validation | per-source CTEs to avoid fan-out |

## Avoiding join fan-out

Orders (1) → order_items (many). Summing an order-level column such as `net_revenue_usd` after joining to items counts it once per line. The scripts avoid this in two ways:
- **Aggregate first, then join** (`03` §5 and `14`: item totals per order, and each customer-level source in its own CTE).
- **Use line-level columns at line grain** (`05`: `line_revenue_usd` and `line_cost_usd`, never order totals).

Marketing has no customer key and is only combined with orders after both sides are aggregated to the same grain (`13`, last query).

## Troubleshooting

| Problem | Fix |
|---|---|
| `could not open file "data/raw/..."` | Run psql from the repository root. |
| `relation "orders" does not exist` | Run `SET search_path TO retailpulse;` first (each script does). |
| Foreign-key violation on load | Load parents before children (the order in `02_load_data.sql`). |
| Re-running from scratch | `01_schema.sql` drops and recreates the `retailpulse` schema. |
