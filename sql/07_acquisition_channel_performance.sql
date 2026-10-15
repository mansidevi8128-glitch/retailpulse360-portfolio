-- =============================================================================
-- 07 — Acquisition-channel performance and 12-month customer value.
-- First-year value uses customers who signed up between 2024-01-01 (start of
-- order history) and 2025-05-31 (a full 365 days before the snapshot), so
-- every channel is compared on the same observation window.
-- =============================================================================

SET search_path TO retailpulse;

-- Lifetime-to-date performance by acquisition channel.
WITH channel_customers AS (
    SELECT acquisition_channel, COUNT(*) AS customers FROM customers GROUP BY 1
),
channel_orders AS (
    SELECT c.acquisition_channel,
           SUM(o.net_revenue_usd) AS net_revenue_usd,
           SUM(o.profit_usd)      AS profit_usd,
           COUNT(*) FILTER (WHERE o.order_status = 'Completed') AS completed_orders
    FROM orders o JOIN customers c USING (customer_id)
    GROUP BY 1
)
SELECT cc.acquisition_channel, cc.customers, co.completed_orders, co.net_revenue_usd, co.profit_usd,
       ROUND(co.net_revenue_usd / cc.customers, 2) AS revenue_per_customer_usd
FROM channel_customers cc JOIN channel_orders co USING (acquisition_channel)
ORDER BY co.net_revenue_usd DESC;

-- First-year (365-day) value per customer by channel.
CREATE OR REPLACE VIEW first_year_value_v AS
WITH eligible AS (
    SELECT customer_id, acquisition_channel, signup_date
    FROM customers
    WHERE signup_date BETWEEN DATE '2024-01-01' AND DATE '2026-05-31' - 365
),
first_year_orders AS (
    SELECT e.customer_id,
           SUM(o.net_revenue_usd) AS revenue_usd,
           SUM(o.profit_usd)      AS profit_usd
    FROM eligible e
    JOIN orders o ON o.customer_id = e.customer_id
                 AND o.order_date < e.signup_date + 365
    GROUP BY e.customer_id
)
SELECT
    e.acquisition_channel,
    COUNT(*)                                                    AS cohort_customers,
    ROUND(AVG(COALESCE(f.revenue_usd, 0)), 2)                   AS first_year_revenue_per_customer_usd,
    ROUND(AVG(COALESCE(f.profit_usd, 0)), 2)                    AS first_year_profit_per_customer_usd,
    ROUND(100.0 * AVG((COALESCE(f.revenue_usd, 0) > 0)::int), 2) AS share_with_purchase_pct
FROM eligible e
LEFT JOIN first_year_orders f ON f.customer_id = e.customer_id
GROUP BY e.acquisition_channel;

SELECT * FROM first_year_value_v ORDER BY first_year_profit_per_customer_usd DESC;

-- Unit economics: spend per new customer vs first-year profit per customer.
-- Attribution assumption: a customer's recorded acquisition_channel received
-- the credit; this is not an incrementality measurement.
WITH spend AS (
    SELECT channel AS acquisition_channel, SUM(spend_usd) AS spend_usd
    FROM marketing_spend GROUP BY 1
),
new_customers AS (
    SELECT acquisition_channel, COUNT(*) AS new_customers
    FROM customers
    WHERE signup_date BETWEEN (SELECT MIN(month) FROM marketing_spend)
                          AND (SELECT (MAX(month) + INTERVAL '1 month - 1 day')::date FROM marketing_spend)
    GROUP BY 1
)
SELECT
    s.acquisition_channel,
    s.spend_usd,
    n.new_customers,
    ROUND(s.spend_usd / n.new_customers, 2)                                           AS spend_per_new_customer_usd,
    v.first_year_profit_per_customer_usd,
    ROUND(s.spend_usd / n.new_customers / v.first_year_profit_per_customer_usd, 2)    AS spend_to_first_year_profit_ratio
FROM spend s
JOIN new_customers n USING (acquisition_channel)
JOIN first_year_value_v v USING (acquisition_channel)
ORDER BY spend_per_new_customer_usd DESC;
