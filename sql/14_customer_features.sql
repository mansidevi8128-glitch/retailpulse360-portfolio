-- =============================================================================
-- 14 — Customer-level feature table for modeling (snapshot 2026-05-31).
-- Rebuilds the provided customer_modeling_snapshot from raw tables using only
-- events on or before the snapshot date, then compares the two.
-- Every aggregate is computed at customer grain in its own CTE BEFORE joining,
-- so orders, sessions and tickets never multiply each other (no fan-out).
-- =============================================================================

SET search_path TO retailpulse;

CREATE OR REPLACE VIEW customer_features_v AS
WITH params AS (
    SELECT DATE '2026-05-31' AS snapshot_date
),
orders_12m AS (
    SELECT o.*
    FROM orders o, params p
    WHERE o.order_date BETWEEN p.snapshot_date - 365 AND p.snapshot_date
),
completed_12m AS (
    SELECT customer_id,
           MAX(order_date)      AS last_order_12m,
           COUNT(*)             AS frequency_12m,
           SUM(net_revenue_usd) AS monetary_value_12m,
           SUM(profit_usd)      AS profit_12m,
           AVG(discount_pct)    AS avg_discount_pct_12m
    FROM orders_12m
    WHERE order_status = 'Completed'
    GROUP BY customer_id
),
refunds_12m AS (
    SELECT customer_id, AVG((order_status = 'Refunded')::int) AS refund_rate_12m
    FROM orders_12m
    GROUP BY customer_id
),
categories_12m AS (
    SELECT o.customer_id, COUNT(DISTINCT p.category) AS category_diversity_12m
    FROM orders_12m o
    JOIN order_items oi ON oi.order_id = o.order_id
    JOIN products p     ON p.product_id = oi.product_id
    WHERE o.order_status = 'Completed'
    GROUP BY o.customer_id
),
web_90d AS (
    SELECT w.customer_id,
           COUNT(*)             AS web_sessions_90d,
           AVG(session_minutes) AS avg_session_minutes_90d,
           SUM(product_views)   AS product_views_90d,
           SUM(cart_adds)       AS cart_adds_90d,
           SUM(converted)       AS conversions_90d
    FROM web_sessions w, params p
    WHERE w.session_date BETWEEN p.snapshot_date - 90 AND p.snapshot_date
    GROUP BY w.customer_id
),
support_12m AS (
    SELECT t.customer_id,
           COUNT(*)              AS support_tickets_12m,
           AVG(resolution_hours) AS avg_resolution_hours_12m,
           AVG(csat_score)       AS avg_csat_12m,
           SUM(refunded)         AS refund_requests_12m
    FROM support_tickets t, params p
    WHERE t.opened_date BETWEEN p.snapshot_date - 365 AND p.snapshot_date
    GROUP BY t.customer_id
),
last_purchase_any AS (
    SELECT o.customer_id, MAX(o.order_date) AS last_purchase_date
    FROM orders o, params p
    WHERE o.order_status = 'Completed' AND o.order_date <= p.snapshot_date
    GROUP BY o.customer_id
)
SELECT
    c.customer_id,
    p.snapshot_date,
    c.region,
    c.acquisition_channel,
    c.preferred_device,
    c.loyalty_tier,
    p.snapshot_date - c.signup_date                                                    AS days_since_signup,
    -- Snapshot convention (reproduced): signup + 30 days when no purchase in 12 months.
    COALESCE(p.snapshot_date - cm.last_order_12m, p.snapshot_date - c.signup_date + 30) AS recency_days,
    -- Corrected recency over all observed history (used by the models).
    COALESCE(p.snapshot_date - lp.last_purchase_date, p.snapshot_date - c.signup_date)  AS days_since_last_purchase,
    (lp.customer_id IS NULL)::int                                                      AS never_purchased,
    COALESCE(cm.frequency_12m, 0)                                                      AS frequency_12m,
    COALESCE(cm.monetary_value_12m, 0)                                                 AS monetary_value_12m,
    COALESCE(cm.monetary_value_12m / NULLIF(cm.frequency_12m, 0), 0)                   AS avg_order_value_12m,
    COALESCE(cm.profit_12m, 0)                                                         AS profit_12m,
    COALESCE(cm.profit_12m / NULLIF(cm.monetary_value_12m, 0), 0)                      AS gross_margin_pct_12m,
    COALESCE(cm.avg_discount_pct_12m, 0)                                               AS avg_discount_pct_12m,
    COALESCE(r.refund_rate_12m, 0)                                                     AS refund_rate_12m,
    COALESCE(cat.category_diversity_12m, 0)                                            AS category_diversity_12m,
    COALESCE(w.web_sessions_90d, 0)                                                    AS web_sessions_90d,
    COALESCE(w.avg_session_minutes_90d, 0)                                             AS avg_session_minutes_90d,
    COALESCE(w.product_views_90d, 0)                                                   AS product_views_90d,
    COALESCE(w.cart_adds_90d, 0)                                                       AS cart_adds_90d,
    COALESCE(w.conversions_90d::numeric / NULLIF(w.web_sessions_90d, 0), 0)            AS conversion_rate_90d,
    COALESCE(w.cart_adds_90d::numeric / NULLIF(w.product_views_90d, 0), 0)             AS cart_add_rate_90d,
    COALESCE(s.support_tickets_12m, 0)                                                 AS support_tickets_12m,
    COALESCE(s.avg_resolution_hours_12m, 0)                                            AS avg_resolution_hours_12m,
    COALESCE(s.avg_csat_12m, 4.0)                                                      AS avg_csat_12m,  -- snapshot imputes 4.0 when no tickets
    COALESCE(s.refund_requests_12m, 0)                                                 AS refund_requests_12m
FROM customers c
CROSS JOIN params p
LEFT JOIN completed_12m     cm  ON cm.customer_id  = c.customer_id
LEFT JOIN refunds_12m       r   ON r.customer_id   = c.customer_id
LEFT JOIN categories_12m    cat ON cat.customer_id = c.customer_id
LEFT JOIN web_90d           w   ON w.customer_id   = c.customer_id
LEFT JOIN support_12m       s   ON s.customer_id   = c.customer_id
LEFT JOIN last_purchase_any lp  ON lp.customer_id  = c.customer_id
WHERE c.signup_date <= p.snapshot_date;

-- Validation: mismatches between rebuilt features and the provided snapshot
-- (tolerance 0.01). Expected: 0 for every feature.
SELECT
    COUNT(*)                                                                                  AS customers_compared,
    COUNT(*) FILTER (WHERE f.days_since_signup       <> s.days_since_signup)                  AS days_since_signup_mismatch,
    COUNT(*) FILTER (WHERE f.recency_days            <> s.recency_days)                       AS recency_mismatch,
    COUNT(*) FILTER (WHERE f.frequency_12m           <> s.frequency_12m)                      AS frequency_mismatch,
    COUNT(*) FILTER (WHERE ABS(f.monetary_value_12m  - s.monetary_value_12m) > 0.01)          AS monetary_mismatch,
    COUNT(*) FILTER (WHERE ABS(f.profit_12m          - s.profit_12m) > 0.01)                  AS profit_mismatch,
    COUNT(*) FILTER (WHERE ABS(f.refund_rate_12m     - s.refund_rate_12m) > 0.01)             AS refund_rate_mismatch,
    COUNT(*) FILTER (WHERE f.category_diversity_12m  <> s.category_diversity_12m)             AS category_mismatch,
    COUNT(*) FILTER (WHERE f.web_sessions_90d        <> s.web_sessions_90d)                   AS sessions_mismatch,
    COUNT(*) FILTER (WHERE ABS(f.conversion_rate_90d - s.conversion_rate_90d) > 0.01)         AS conversion_mismatch,
    COUNT(*) FILTER (WHERE f.support_tickets_12m     <> s.support_tickets_12m)                AS tickets_mismatch,
    COUNT(*) FILTER (WHERE ABS(f.avg_csat_12m        - s.avg_csat_12m) > 0.01)                AS csat_mismatch
FROM customer_features_v f
JOIN customer_modeling_snapshot s USING (customer_id);

-- How many customers carry the recency sentinel, and how many of them did buy earlier.
SELECT COUNT(*) FILTER (WHERE frequency_12m = 0)                         AS no_purchase_12m,
       COUNT(*) FILTER (WHERE frequency_12m = 0 AND never_purchased = 0) AS sentinel_but_bought_before,
       COUNT(*) FILTER (WHERE never_purchased = 1)                       AS never_purchased
FROM customer_features_v;
