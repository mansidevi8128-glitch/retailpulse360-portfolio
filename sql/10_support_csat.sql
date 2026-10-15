-- =============================================================================
-- 10 — Support tickets, resolution time and customer satisfaction (CSAT 1-5).
-- "Satisfied" = CSAT >= 4.
-- =============================================================================

SET search_path TO retailpulse;

-- By issue type.
SELECT issue_type,
       COUNT(*)                                                        AS tickets,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)              AS ticket_share_pct,
       ROUND(AVG(resolution_hours), 2)                                 AS avg_resolution_hours,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY resolution_hours)   AS median_resolution_hours,
       ROUND(AVG(csat_score), 2)                                       AS avg_csat,
       ROUND(100.0 * AVG((csat_score >= 4)::int), 2)                   AS satisfied_pct,
       ROUND(100.0 * AVG(refunded), 2)                                 AS refunded_pct
FROM support_tickets
GROUP BY issue_type
ORDER BY tickets DESC;

-- By priority.
SELECT priority,
       COUNT(*)                                        AS tickets,
       ROUND(AVG(resolution_hours), 2)                 AS avg_resolution_hours,
       ROUND(AVG(csat_score), 2)                       AS avg_csat,
       ROUND(100.0 * AVG((csat_score >= 4)::int), 2)   AS satisfied_pct
FROM support_tickets
GROUP BY priority
ORDER BY avg_resolution_hours;

-- CSAT by resolution-time band.
SELECT CASE WHEN resolution_hours <= 8 THEN '<8h'
            WHEN resolution_hours <= 24 THEN '8-24h'
            WHEN resolution_hours <= 48 THEN '24-48h'
            ELSE '48h+' END                            AS resolution_band,
       COUNT(*)                                        AS tickets,
       ROUND(AVG(csat_score), 2)                       AS avg_csat,
       ROUND(100.0 * AVG((csat_score >= 4)::int), 2)   AS satisfied_pct
FROM support_tickets
GROUP BY 1
ORDER BY MIN(resolution_hours);

-- Monthly support load relative to fulfilled orders.
WITH monthly_tickets AS (
    SELECT DATE_TRUNC('month', opened_date)::date AS month, COUNT(*) AS tickets, AVG(csat_score) AS avg_csat
    FROM support_tickets GROUP BY 1
),
monthly_orders AS (
    SELECT DATE_TRUNC('month', order_date)::date AS month,
           COUNT(*) FILTER (WHERE order_status IN ('Completed', 'Refunded')) AS fulfilled_orders
    FROM orders GROUP BY 1
)
SELECT t.month, t.tickets, o.fulfilled_orders,
       ROUND(100.0 * t.tickets / o.fulfilled_orders, 2) AS tickets_per_100_orders,
       ROUND(t.avg_csat, 2)                             AS avg_csat
FROM monthly_tickets t
JOIN monthly_orders o USING (month)
ORDER BY t.month;
