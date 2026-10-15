-- =============================================================================
-- 08 — Repeat purchase and purchase-frequency distribution (Completed orders).
-- =============================================================================

SET search_path TO retailpulse;

WITH orders_per_customer AS (
    SELECT c.customer_id,
           COUNT(o.order_id) AS completed_orders
    FROM customers c
    LEFT JOIN orders o ON o.customer_id = c.customer_id AND o.order_status = 'Completed'
    GROUP BY c.customer_id
),
banded AS (
    SELECT customer_id, completed_orders,
           CASE
               WHEN completed_orders = 0 THEN '0'
               WHEN completed_orders = 1 THEN '1'
               WHEN completed_orders = 2 THEN '2'
               WHEN completed_orders <= 4 THEN '3-4'
               WHEN completed_orders <= 9 THEN '5-9'
               ELSE '10+'
           END AS frequency_band,
           CASE
               WHEN completed_orders = 0 THEN 0 WHEN completed_orders = 1 THEN 1 WHEN completed_orders = 2 THEN 2
               WHEN completed_orders <= 4 THEN 3 WHEN completed_orders <= 9 THEN 4 ELSE 5
           END AS band_order
    FROM orders_per_customer
)
SELECT frequency_band,
       COUNT(*)                                          AS customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_pct
FROM banded
GROUP BY frequency_band, band_order
ORDER BY band_order;

-- Repeat-purchase rate among purchasing customers.
WITH orders_per_customer AS (
    SELECT customer_id, COUNT(*) AS completed_orders
    FROM orders
    WHERE order_status = 'Completed'
    GROUP BY customer_id
)
SELECT COUNT(*)                                                         AS purchasing_customers,
       COUNT(*) FILTER (WHERE completed_orders >= 2)                    AS repeat_customers,
       ROUND(100.0 * COUNT(*) FILTER (WHERE completed_orders >= 2) / COUNT(*), 2) AS repeat_purchase_rate_pct,
       ROUND(AVG(completed_orders), 2)                                  AS avg_orders_per_buyer
FROM orders_per_customer;

-- Days between consecutive completed orders (LAG window function).
WITH ordered AS (
    SELECT customer_id, order_date,
           order_date - LAG(order_date) OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS days_since_previous
    FROM orders
    WHERE order_status = 'Completed'
)
SELECT ROUND(AVG(days_since_previous), 1)                                             AS avg_days_between_orders,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_since_previous)               AS median_days_between_orders
FROM ordered
WHERE days_since_previous IS NOT NULL;
