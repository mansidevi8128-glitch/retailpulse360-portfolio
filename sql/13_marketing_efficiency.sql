-- =============================================================================
-- 13 — Marketing spend, CTR, CPC and cost-per-lead.
-- Marketing data is at month x channel grain and has no customer key, so it is
-- never joined row-by-row to orders (that would fan out spend).
-- =============================================================================

SET search_path TO retailpulse;

-- Channel totals.
SELECT channel,
       SUM(spend_usd)                                              AS spend_usd,
       SUM(impressions)                                            AS impressions,
       SUM(clicks)                                                 AS clicks,
       SUM(leads)                                                  AS leads,
       ROUND(100.0 * SUM(clicks) / SUM(impressions), 2)            AS ctr_pct,
       ROUND(SUM(spend_usd) / SUM(clicks), 2)                      AS cpc_usd,
       ROUND(100.0 * SUM(leads) / SUM(clicks), 2)                  AS click_to_lead_pct,
       ROUND(SUM(spend_usd) / SUM(leads), 2)                       AS cost_per_lead_usd,
       ROUND(100 * SUM(spend_usd) / SUM(SUM(spend_usd)) OVER (), 2) AS spend_share_pct
FROM marketing_spend
GROUP BY channel
ORDER BY spend_usd DESC;

-- Monthly totals with month-over-month spend change.
SELECT month,
       SUM(spend_usd)                                                         AS spend_usd,
       ROUND(SUM(spend_usd) / SUM(leads), 2)                                  AS cost_per_lead_usd,
       ROUND(100.0 * SUM(clicks) / SUM(impressions), 2)                       AS ctr_pct,
       ROUND(100 * (SUM(spend_usd) / LAG(SUM(spend_usd)) OVER (ORDER BY month) - 1), 2) AS spend_mom_pct
FROM marketing_spend
GROUP BY month
ORDER BY month;

-- Marketing spend vs product-level profit by year (aggregate grain on both sides).
WITH spend AS (
    SELECT EXTRACT(YEAR FROM month)::int AS year, SUM(spend_usd) AS marketing_spend_usd
    FROM marketing_spend GROUP BY 1
),
profit AS (
    SELECT EXTRACT(YEAR FROM order_date)::int AS year, SUM(net_revenue_usd) AS net_revenue_usd, SUM(profit_usd) AS profit_usd
    FROM orders GROUP BY 1
)
SELECT year, net_revenue_usd, profit_usd, marketing_spend_usd,
       profit_usd - marketing_spend_usd                          AS profit_after_marketing_usd,
       ROUND(100 * marketing_spend_usd / net_revenue_usd, 2)     AS marketing_pct_of_revenue
FROM profit JOIN spend USING (year)
ORDER BY year;
