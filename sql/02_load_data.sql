-- =============================================================================
-- Load the CSV files with psql's client-side \copy.
-- Run from the REPOSITORY ROOT so the relative paths resolve:
--   psql -d retailpulse360 -v ON_ERROR_STOP=1 -f sql/02_load_data.sql
-- Parents are loaded before children so foreign keys validate on insert.
-- =============================================================================

SET search_path TO retailpulse;

\copy customers                  FROM 'data/raw/customers.csv'                         WITH (FORMAT csv, HEADER true)
\copy products                   FROM 'data/raw/products.csv'                          WITH (FORMAT csv, HEADER true)
\copy orders                     FROM 'data/raw/orders.csv'                            WITH (FORMAT csv, HEADER true)
\copy order_items                FROM 'data/raw/order_items.csv'                       WITH (FORMAT csv, HEADER true)
\copy web_sessions               FROM 'data/raw/web_sessions.csv'                      WITH (FORMAT csv, HEADER true)
\copy support_tickets            FROM 'data/raw/support_tickets.csv'                   WITH (FORMAT csv, HEADER true)
\copy marketing_spend            FROM 'data/raw/marketing_spend.csv'                   WITH (FORMAT csv, HEADER true)
\copy customer_modeling_snapshot FROM 'data/processed/customer_modeling_snapshot.csv'  WITH (FORMAT csv, HEADER true)

ANALYZE;

-- Row counts after loading (expected values from docs/dataset_notes.md).
SELECT 'customers' AS table_name, COUNT(*) AS row_count, 6000 AS expected FROM customers
UNION ALL SELECT 'products', COUNT(*), 120 FROM products
UNION ALL SELECT 'orders', COUNT(*), 30054 FROM orders
UNION ALL SELECT 'order_items', COUNT(*), 56183 FROM order_items
UNION ALL SELECT 'web_sessions', COUNT(*), 76327 FROM web_sessions
UNION ALL SELECT 'support_tickets', COUNT(*), 4662 FROM support_tickets
UNION ALL SELECT 'marketing_spend', COUNT(*), 174 FROM marketing_spend
UNION ALL SELECT 'customer_modeling_snapshot', COUNT(*), 6000 FROM customer_modeling_snapshot;
