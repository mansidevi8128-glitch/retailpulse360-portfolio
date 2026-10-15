-- =============================================================================
-- 06 — Regional customer and revenue analysis.
-- Orders are aggregated to region grain separately from the customer count
-- so customers without orders are still counted.
-- =============================================================================

SET search_path TO retailpulse;

WITH customer_counts AS (
    SELECT region, COUNT(*) AS customers
    FROM customers
    GROUP BY region
),
order_totals AS (
    SELECT
        c.region,
        COUNT(DISTINCT o.customer_id) FILTER (WHERE o.order_status = 'Completed') AS purchasing_customers,
        COUNT(*) FILTER (WHERE o.order_status = 'Completed')                      AS completed_orders,
        COUNT(*) FILTER (WHERE o.order_status = 'Refunded')                       AS refunded_orders,
        SUM(o.net_revenue_usd)                                                    AS net_revenue_usd,
        SUM(o.profit_usd)                                                         AS profit_usd
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    GROUP BY c.region
)
SELECT
    cc.region,
    cc.customers,
    ot.purchasing_customers,
    ot.completed_orders,
    ot.net_revenue_usd,
    ot.profit_usd,
    ROUND(ot.net_revenue_usd / ot.completed_orders, 2)                                  AS aov_usd,
    ROUND(ot.net_revenue_usd / cc.customers, 2)                                         AS revenue_per_customer_usd,
    ROUND(100.0 * ot.refunded_orders / (ot.completed_orders + ot.refunded_orders), 2)   AS refund_rate_pct,
    ROUND(100 * ot.net_revenue_usd / SUM(ot.net_revenue_usd) OVER (), 2)                AS revenue_share_pct
FROM customer_counts cc
JOIN order_totals ot USING (region)
ORDER BY ot.net_revenue_usd DESC;

-- Top 5 states by revenue per customer (minimum 150 customers).
WITH state_totals AS (
    SELECT c.state, c.region, COUNT(DISTINCT c.customer_id) AS customers, COALESCE(SUM(o.net_revenue_usd), 0) AS net_revenue_usd
    FROM customers c
    LEFT JOIN orders o ON o.customer_id = c.customer_id
    GROUP BY c.state, c.region
)
SELECT state, region, customers, net_revenue_usd, ROUND(net_revenue_usd / customers, 2) AS revenue_per_customer_usd
FROM state_totals
WHERE customers >= 150
ORDER BY revenue_per_customer_usd DESC
LIMIT 5;
