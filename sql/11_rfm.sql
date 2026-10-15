-- =============================================================================
-- 11 — RFM (recency, frequency, monetary) at customer level.
-- Based on Completed orders up to the snapshot date (2026-05-31).
-- Scores are quintiles (NTILE 5) among purchasing customers: 5 = best.
-- Customers with no completed order get score 1 on all three dimensions.
-- =============================================================================

SET search_path TO retailpulse;

CREATE OR REPLACE VIEW customer_rfm_v AS
WITH params AS (
    SELECT DATE '2026-05-31' AS snapshot_date
),
purchases AS (
    SELECT customer_id,
           MAX(order_date)      AS last_order_date,
           COUNT(*)             AS frequency,
           SUM(net_revenue_usd) AS monetary_usd
    FROM orders
    WHERE order_status = 'Completed'
      AND order_date <= (SELECT snapshot_date FROM params)
    GROUP BY customer_id
),
scored AS (
    SELECT p.*,
           (SELECT snapshot_date FROM params) - last_order_date              AS recency_days,
           NTILE(5) OVER (ORDER BY last_order_date ASC, customer_id)         AS r_score,
           NTILE(5) OVER (ORDER BY frequency ASC, customer_id)               AS f_score,
           NTILE(5) OVER (ORDER BY monetary_usd ASC, customer_id)            AS m_score
    FROM purchases p
)
SELECT c.customer_id,
       COALESCE(s.recency_days, (SELECT snapshot_date FROM params) - c.signup_date) AS recency_days,
       COALESCE(s.frequency, 0)    AS frequency,
       COALESCE(s.monetary_usd, 0) AS monetary_usd,
       COALESCE(s.r_score, 1)      AS r_score,
       COALESCE(s.f_score, 1)      AS f_score,
       COALESCE(s.m_score, 1)      AS m_score,
       CASE
           WHEN s.customer_id IS NULL                       THEN 'No purchase'
           WHEN s.r_score >= 4 AND s.f_score >= 4           THEN 'Champions'
           WHEN s.r_score >= 3 AND s.f_score >= 3           THEN 'Loyal'
           WHEN s.r_score >= 4 AND s.f_score <= 2           THEN 'Promising'
           WHEN s.r_score <= 2 AND s.f_score >= 3           THEN 'At risk'
           ELSE 'Hibernating'
       END AS rfm_group
FROM customers c
LEFT JOIN scored s ON s.customer_id = c.customer_id;

-- Size and value of each RFM group, with observed churn (descriptive only).
SELECT r.rfm_group,
       COUNT(*)                                           AS customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_pct,
       ROUND(AVG(r.recency_days), 1)                      AS avg_recency_days,
       ROUND(AVG(r.frequency), 2)                         AS avg_frequency,
       ROUND(AVG(r.monetary_usd), 2)                      AS avg_monetary_usd,
       ROUND(100.0 * AVG(s.churned_next_90d), 2)          AS churn_rate_pct
FROM customer_rfm_v r
JOIN customer_modeling_snapshot s USING (customer_id)
GROUP BY r.rfm_group
ORDER BY avg_monetary_usd DESC;
