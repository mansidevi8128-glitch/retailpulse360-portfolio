-- =============================================================================
-- 05 — Product and category profitability (line-item grain).
-- Joining order_items -> orders is many-to-one, so bringing order_status down
-- to the line does NOT duplicate anything. Never sum order-level money fields
-- after this join; use line_revenue_usd / line_cost_usd instead.
-- Category revenue excludes shipping fees.
-- =============================================================================

SET search_path TO retailpulse;

CREATE OR REPLACE VIEW line_financials_v AS
SELECT
    oi.order_item_id,
    oi.order_id,
    o.order_date,
    o.order_status,
    p.product_id,
    p.category,
    p.subcategory,
    oi.quantity,
    CASE WHEN o.order_status = 'Completed' THEN oi.line_revenue_usd ELSE 0 END                 AS revenue_usd,
    CASE WHEN o.order_status IN ('Completed', 'Refunded') THEN oi.line_cost_usd ELSE 0 END     AS cost_usd,
    CASE WHEN o.order_status = 'Refunded' THEN oi.line_cost_usd ELSE 0 END                     AS refund_loss_usd
FROM order_items oi
JOIN orders   o ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id;

-- Category ranking by revenue, profit and margin.
WITH category_totals AS (
    SELECT
        category,
        COUNT(DISTINCT product_id)                                          AS products,
        SUM(quantity) FILTER (WHERE order_status = 'Completed')             AS units_sold,
        SUM(revenue_usd)                                                    AS revenue_usd,
        SUM(revenue_usd) - SUM(cost_usd)                                    AS profit_usd,
        SUM(refund_loss_usd)                                                AS refund_loss_usd,
        COUNT(*) FILTER (WHERE order_status = 'Refunded')                   AS refunded_lines,
        COUNT(*) FILTER (WHERE order_status IN ('Completed', 'Refunded'))   AS fulfilled_lines
    FROM line_financials_v
    GROUP BY category
)
SELECT
    category,
    products,
    units_sold,
    revenue_usd,
    profit_usd,
    refund_loss_usd,
    ROUND(100 * profit_usd / NULLIF(revenue_usd, 0), 2)              AS gross_margin_pct,
    ROUND(100 * revenue_usd / SUM(revenue_usd) OVER (), 2)           AS revenue_share_pct,
    ROUND(100.0 * refunded_lines / NULLIF(fulfilled_lines, 0), 2)    AS line_refund_rate_pct,
    RANK() OVER (ORDER BY revenue_usd DESC)                          AS revenue_rank,
    RANK() OVER (ORDER BY profit_usd DESC)                           AS profit_rank,
    RANK() OVER (ORDER BY profit_usd / NULLIF(revenue_usd, 0) DESC)  AS margin_rank
FROM category_totals
ORDER BY revenue_usd DESC;

-- Top 3 products by profit within each category.
WITH product_profit AS (
    SELECT category, subcategory, product_id,
           SUM(revenue_usd)                  AS revenue_usd,
           SUM(revenue_usd) - SUM(cost_usd)  AS profit_usd
    FROM line_financials_v
    GROUP BY category, subcategory, product_id
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY category ORDER BY profit_usd DESC) AS rank_in_category
    FROM product_profit
)
SELECT category, rank_in_category, product_id, subcategory, revenue_usd, profit_usd,
       ROUND(100 * profit_usd / NULLIF(revenue_usd, 0), 2) AS margin_pct
FROM ranked
WHERE rank_in_category <= 3
ORDER BY category, rank_in_category;

-- Reconciliation: categories + shipping revenue = total net revenue.
SELECT
    (SELECT SUM(revenue_usd) FROM line_financials_v)                                         AS category_revenue_usd,
    (SELECT SUM(shipping_fee_usd) FROM orders WHERE order_status = 'Completed')              AS shipping_revenue_usd,
    (SELECT SUM(net_revenue_usd) FROM orders)                                                AS total_net_revenue_usd;
