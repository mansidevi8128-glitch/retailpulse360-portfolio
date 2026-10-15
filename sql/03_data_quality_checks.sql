-- =============================================================================
-- 03 — Data-quality checks: row counts, key uniqueness, missing values,
--      referential integrity and business rules.
-- A healthy result is 0 in every "violations" column unless noted.
-- =============================================================================

SET search_path TO retailpulse;

-- 1. Primary-key uniqueness (constraints already enforce this; the query
--    documents the check for databases loaded without constraints).
SELECT 'customers' AS table_name, COUNT(*) - COUNT(DISTINCT customer_id) AS duplicate_keys FROM customers
UNION ALL SELECT 'products', COUNT(*) - COUNT(DISTINCT product_id) FROM products
UNION ALL SELECT 'orders', COUNT(*) - COUNT(DISTINCT order_id) FROM orders
UNION ALL SELECT 'order_items', COUNT(*) - COUNT(DISTINCT order_item_id) FROM order_items
UNION ALL SELECT 'web_sessions', COUNT(*) - COUNT(DISTINCT session_id) FROM web_sessions
UNION ALL SELECT 'support_tickets', COUNT(*) - COUNT(DISTINCT ticket_id) FROM support_tickets
UNION ALL SELECT 'marketing_spend', COUNT(*) - COUNT(DISTINCT (month, channel)) FROM marketing_spend;

-- 2. Missing values in key business columns.
SELECT
    COUNT(*) FILTER (WHERE customer_id IS NULL)     AS null_customer_id,
    COUNT(*) FILTER (WHERE order_date IS NULL)      AS null_order_date,
    COUNT(*) FILTER (WHERE order_status IS NULL)    AS null_order_status,
    COUNT(*) FILTER (WHERE net_revenue_usd IS NULL) AS null_net_revenue
FROM orders;

-- 3. Referential integrity (orphan child rows).
SELECT 'orders -> customers' AS relationship, COUNT(*) AS orphan_rows
FROM orders o LEFT JOIN customers c ON c.customer_id = o.customer_id WHERE c.customer_id IS NULL
UNION ALL
SELECT 'order_items -> orders', COUNT(*)
FROM order_items oi LEFT JOIN orders o ON o.order_id = oi.order_id WHERE o.order_id IS NULL
UNION ALL
SELECT 'order_items -> products', COUNT(*)
FROM order_items oi LEFT JOIN products p ON p.product_id = oi.product_id WHERE p.product_id IS NULL
UNION ALL
SELECT 'web_sessions -> customers', COUNT(*)
FROM web_sessions w LEFT JOIN customers c ON c.customer_id = w.customer_id WHERE c.customer_id IS NULL
UNION ALL
SELECT 'support_tickets -> customers', COUNT(*)
FROM support_tickets t LEFT JOIN customers c ON c.customer_id = t.customer_id WHERE c.customer_id IS NULL
UNION ALL
SELECT 'orders without items', COUNT(*)
FROM orders o WHERE NOT EXISTS (SELECT 1 FROM order_items oi WHERE oi.order_id = o.order_id);

-- 4. Date ranges.
SELECT 'customers.signup_date' AS column_name, MIN(signup_date) AS min_date, MAX(signup_date) AS max_date FROM customers
UNION ALL SELECT 'orders.order_date', MIN(order_date), MAX(order_date) FROM orders
UNION ALL SELECT 'web_sessions.session_date', MIN(session_date), MAX(session_date) FROM web_sessions
UNION ALL SELECT 'support_tickets.opened_date', MIN(opened_date), MAX(opened_date) FROM support_tickets
UNION ALL SELECT 'marketing_spend.month', MIN(month), MAX(month) FROM marketing_spend;

-- 5. Order-to-line-item reconciliation by status. Line items are aggregated
--    to order grain FIRST so the join is one-to-one (no fan-out).
WITH item_totals AS (
    SELECT order_id,
           SUM(line_revenue_usd) AS line_revenue_usd,
           SUM(line_cost_usd)    AS line_cost_usd
    FROM order_items
    GROUP BY order_id
)
SELECT
    o.order_status,
    COUNT(*)                                                                                         AS orders,
    COUNT(*) FILTER (WHERE ABS(o.gross_merchandise_value_usd - i.line_revenue_usd) > 0.01)           AS gmv_vs_lines_violations,
    COUNT(*) FILTER (WHERE ABS(o.profit_usd - (o.net_revenue_usd - o.total_cost_usd)) > 0.01)        AS profit_formula_violations,
    COUNT(*) FILTER (WHERE o.order_status = 'Completed'
                       AND ABS(o.net_revenue_usd - (o.gross_merchandise_value_usd + o.shipping_fee_usd)) > 0.01) AS completed_net_revenue_violations,
    COUNT(*) FILTER (WHERE o.order_status = 'Refunded' AND o.net_revenue_usd <> 0)                   AS refunded_with_revenue,
    COUNT(*) FILTER (WHERE o.order_status = 'Cancelled' AND (o.net_revenue_usd <> 0 OR o.total_cost_usd <> 0)) AS cancelled_with_value
FROM orders o
JOIN item_totals i ON i.order_id = o.order_id
GROUP BY o.order_status
ORDER BY o.order_status;

-- 6. Business-rule checks (non-zero counts are findings to explain).
SELECT 'orders before customer signup' AS check_name, COUNT(*) AS rows_flagged
FROM orders o JOIN customers c USING (customer_id) WHERE o.order_date < c.signup_date
UNION ALL
SELECT 'coupon_used = 1 but discount_pct = 0', COUNT(*) FROM orders WHERE coupon_used = 1 AND discount_pct = 0
UNION ALL
SELECT 'completed orders with negative profit', COUNT(*) FROM orders WHERE order_status = 'Completed' AND profit_usd < 0
UNION ALL
SELECT 'line revenue != qty * price * (1 - discount)', COUNT(*)
FROM order_items WHERE ABS(line_revenue_usd - quantity * unit_price_usd * (1 - discount_pct / 100)) > 0.01
UNION ALL
SELECT 'sessions converted without checkout', COUNT(*) FROM web_sessions WHERE converted = 1 AND checkout_started = 0
UNION ALL
SELECT 'marketing clicks > impressions', COUNT(*) FROM marketing_spend WHERE clicks > impressions;

-- 7. Category domains (check for inconsistent spellings).
SELECT 'order_status' AS attribute, order_status AS value, COUNT(*) AS rows FROM orders GROUP BY order_status
UNION ALL SELECT 'sales_channel', sales_channel, COUNT(*) FROM orders GROUP BY sales_channel
UNION ALL SELECT 'region', region, COUNT(*) FROM customers GROUP BY region
UNION ALL SELECT 'acquisition_channel', acquisition_channel, COUNT(*) FROM customers GROUP BY acquisition_channel
ORDER BY attribute, value;
