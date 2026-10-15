-- =============================================================================
-- 09 — Refund analysis.
-- Refund rate = refunded / (completed + refunded); cancelled orders are
-- excluded because they were never fulfilled. Refund loss = merchandise cost
-- of refunded orders (their profit is negative by that amount).
-- =============================================================================

SET search_path TO retailpulse;

-- By sales channel.
SELECT sales_channel,
       COUNT(*) FILTER (WHERE order_status IN ('Completed', 'Refunded'))   AS fulfilled_orders,
       COUNT(*) FILTER (WHERE order_status = 'Refunded')                   AS refunded_orders,
       ROUND(100.0 * COUNT(*) FILTER (WHERE order_status = 'Refunded')
             / COUNT(*) FILTER (WHERE order_status IN ('Completed', 'Refunded')), 2) AS refund_rate_pct,
       -SUM(profit_usd) FILTER (WHERE order_status = 'Refunded')           AS refund_loss_usd
FROM orders
GROUP BY sales_channel
ORDER BY refund_rate_pct DESC;

-- By discount band.
SELECT CASE WHEN discount_pct = 0 THEN '0%'
            WHEN discount_pct <= 10 THEN '1-10%'
            WHEN discount_pct <= 15 THEN '11-15%'
            WHEN discount_pct <= 20 THEN '16-20%'
            ELSE '21%+' END                                                AS discount_band,
       COUNT(*) FILTER (WHERE order_status = 'Completed')                  AS completed_orders,
       ROUND(100.0 * COUNT(*) FILTER (WHERE order_status = 'Refunded')
             / COUNT(*) FILTER (WHERE order_status IN ('Completed', 'Refunded')), 2) AS refund_rate_pct,
       ROUND(100 * SUM(profit_usd) / NULLIF(SUM(net_revenue_usd), 0), 2)   AS profit_margin_pct
FROM orders
GROUP BY 1
ORDER BY MIN(discount_pct);

-- By product category (line grain; uses the view from script 05).
SELECT category,
       COUNT(*) FILTER (WHERE order_status = 'Refunded')                    AS refunded_lines,
       ROUND(100.0 * COUNT(*) FILTER (WHERE order_status = 'Refunded')
             / COUNT(*) FILTER (WHERE order_status IN ('Completed', 'Refunded')), 2) AS line_refund_rate_pct,
       SUM(refund_loss_usd)                                                 AS refund_loss_usd
FROM line_financials_v
GROUP BY category
ORDER BY line_refund_rate_pct DESC;

-- Monthly refund trend.
SELECT DATE_TRUNC('month', order_date)::date AS order_month,
       ROUND(100.0 * COUNT(*) FILTER (WHERE order_status = 'Refunded')
             / COUNT(*) FILTER (WHERE order_status IN ('Completed', 'Refunded')), 2) AS refund_rate_pct
FROM orders
GROUP BY 1
ORDER BY 1;
