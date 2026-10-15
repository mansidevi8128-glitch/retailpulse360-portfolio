-- =============================================================================
-- 12 — Monthly cohort retention.
-- Cohort = month of a customer's first OBSERVED completed order. Order history
-- starts in January 2024 but some customers signed up in 2023, so 2024 cohorts
-- are left-censored (they include returning customers).
-- Retention(N) = share of the cohort with a completed order N months later.
-- =============================================================================

SET search_path TO retailpulse;

CREATE OR REPLACE VIEW cohort_retention_v AS
WITH completed AS (
    SELECT DISTINCT customer_id, DATE_TRUNC('month', order_date)::date AS order_month
    FROM orders
    WHERE order_status = 'Completed'
),
first_purchase AS (
    SELECT customer_id, MIN(order_month) AS cohort_month
    FROM completed
    GROUP BY customer_id
),
activity AS (
    SELECT f.cohort_month,
           (EXTRACT(YEAR FROM c.order_month) - EXTRACT(YEAR FROM f.cohort_month)) * 12
             + (EXTRACT(MONTH FROM c.order_month) - EXTRACT(MONTH FROM f.cohort_month)) AS months_since_first,
           c.customer_id
    FROM completed c
    JOIN first_purchase f USING (customer_id)
),
cohort_sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size FROM first_purchase GROUP BY cohort_month
)
SELECT a.cohort_month,
       s.cohort_size,
       a.months_since_first::int                                          AS months_since_first,
       COUNT(DISTINCT a.customer_id)                                      AS active_customers,
       ROUND(100.0 * COUNT(DISTINCT a.customer_id) / s.cohort_size, 2)    AS retention_pct
FROM activity a
JOIN cohort_sizes s USING (cohort_month)
GROUP BY a.cohort_month, s.cohort_size, a.months_since_first;

-- Retention matrix (first 6 months shown as columns).
SELECT cohort_month,
       cohort_size,
       MAX(retention_pct) FILTER (WHERE months_since_first = 1) AS m1,
       MAX(retention_pct) FILTER (WHERE months_since_first = 2) AS m2,
       MAX(retention_pct) FILTER (WHERE months_since_first = 3) AS m3,
       MAX(retention_pct) FILTER (WHERE months_since_first = 6) AS m6,
       MAX(retention_pct) FILTER (WHERE months_since_first = 12) AS m12
FROM cohort_retention_v
GROUP BY cohort_month, cohort_size
ORDER BY cohort_month;

-- Customer-weighted average retention curve. Only cohorts old enough to be
-- observed at month N are included in the denominator.
WITH observable AS (
    SELECT s.cohort_month, s.cohort_size, n.months_since_first
    FROM (SELECT DISTINCT cohort_month, cohort_size FROM cohort_retention_v) s
    CROSS JOIN generate_series(1, 12) AS n(months_since_first)
    WHERE s.cohort_month + make_interval(months => n.months_since_first) <= DATE '2026-05-01'
)
SELECT o.months_since_first,
       COUNT(*)                                                                         AS cohorts_observed,
       ROUND(100.0 * SUM(COALESCE(r.active_customers, 0)) / SUM(o.cohort_size), 2)      AS retention_pct
FROM observable o
LEFT JOIN cohort_retention_v r
       ON r.cohort_month = o.cohort_month AND r.months_since_first = o.months_since_first
GROUP BY o.months_since_first
ORDER BY o.months_since_first;
