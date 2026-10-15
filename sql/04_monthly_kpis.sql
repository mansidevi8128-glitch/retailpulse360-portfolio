-- =============================================================================
-- 04 — Monthly business KPIs and growth.
-- Definitions: net revenue and AOV use Completed orders only; GMV counts
-- every placed order; profit includes refund losses (negative profit on
-- refunded orders); refund rate = refunded / (completed + refunded).
-- =============================================================================

SET search_path TO retailpulse;

CREATE OR REPLACE VIEW monthly_kpis_v AS
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', order_date)::date                                 AS order_month,
        COUNT(*)                                                              AS orders_placed,
        COUNT(*) FILTER (WHERE order_status = 'Completed')                    AS completed_orders,
        COUNT(*) FILTER (WHERE order_status = 'Refunded')                     AS refunded_orders,
        COUNT(*) FILTER (WHERE order_status = 'Cancelled')                    AS cancelled_orders,
        SUM(gross_merchandise_value_usd)                                      AS gmv_usd,
        SUM(net_revenue_usd)                                                  AS net_revenue_usd,
        SUM(profit_usd)                                                       AS profit_usd,
        COUNT(DISTINCT customer_id) FILTER (WHERE order_status = 'Completed') AS active_customers
    FROM orders
    GROUP BY 1
)
SELECT
    order_month,
    orders_placed,
    completed_orders,
    refunded_orders,
    cancelled_orders,
    gmv_usd,
    net_revenue_usd,
    profit_usd,
    active_customers,
    ROUND(net_revenue_usd / NULLIF(completed_orders, 0), 2)                                AS aov_usd,
    ROUND(100 * profit_usd / NULLIF(net_revenue_usd, 0), 2)                                AS profit_margin_pct,
    ROUND(100.0 * refunded_orders / NULLIF(completed_orders + refunded_orders, 0), 2)      AS refund_rate_pct,
    ROUND(100 * (net_revenue_usd / NULLIF(LAG(net_revenue_usd) OVER w, 0) - 1), 2)         AS revenue_mom_pct,
    ROUND(100 * (profit_usd / NULLIF(LAG(profit_usd) OVER w, 0) - 1), 2)                   AS profit_mom_pct,
    ROUND(100 * (net_revenue_usd / NULLIF(LAG(net_revenue_usd, 12) OVER w, 0) - 1), 2)     AS revenue_yoy_pct
FROM monthly
WINDOW w AS (ORDER BY order_month)
ORDER BY order_month;

SELECT * FROM monthly_kpis_v;

-- Like-for-like year comparison: January-May of each year (2026 data ends in May).
SELECT
    EXTRACT(YEAR FROM order_date)::int                                       AS year,
    SUM(net_revenue_usd)                                                     AS net_revenue_usd,
    SUM(profit_usd)                                                          AS profit_usd,
    COUNT(*) FILTER (WHERE order_status = 'Completed')                       AS completed_orders,
    ROUND(SUM(net_revenue_usd) / COUNT(*) FILTER (WHERE order_status = 'Completed'), 2) AS aov_usd,
    COUNT(DISTINCT customer_id) FILTER (WHERE order_status = 'Completed')    AS purchasing_customers
FROM orders
WHERE EXTRACT(MONTH FROM order_date) <= 5
GROUP BY 1
ORDER BY 1;

-- Whole-period executive summary.
SELECT
    MIN(order_date)                                                                   AS period_start,
    MAX(order_date)                                                                   AS period_end,
    SUM(gross_merchandise_value_usd)                                                  AS gmv_usd,
    SUM(net_revenue_usd)                                                              AS net_revenue_usd,
    SUM(profit_usd)                                                                   AS profit_usd,
    -SUM(profit_usd) FILTER (WHERE order_status = 'Refunded')                         AS refund_loss_usd,
    ROUND(SUM(net_revenue_usd) / COUNT(*) FILTER (WHERE order_status = 'Completed'), 2) AS aov_usd,
    ROUND(100 * SUM(profit_usd) / SUM(net_revenue_usd), 2)                            AS profit_margin_pct
FROM orders;

-- Sales-channel comparison (website / mobile app / marketplace).
SELECT
    sales_channel,
    COUNT(*) FILTER (WHERE order_status = 'Completed')                                    AS completed_orders,
    SUM(net_revenue_usd)                                                                  AS net_revenue_usd,
    SUM(profit_usd)                                                                       AS profit_usd,
    ROUND(SUM(net_revenue_usd) / COUNT(*) FILTER (WHERE order_status = 'Completed'), 2)   AS aov_usd,
    ROUND(100 * SUM(profit_usd) / SUM(net_revenue_usd), 2)                                AS profit_margin_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE order_status = 'Refunded')
          / COUNT(*) FILTER (WHERE order_status IN ('Completed', 'Refunded')), 2)         AS refund_rate_pct,
    ROUND(100 * SUM(net_revenue_usd) / SUM(SUM(net_revenue_usd)) OVER (), 2)              AS revenue_share_pct
FROM orders
GROUP BY sales_channel
ORDER BY net_revenue_usd DESC;
