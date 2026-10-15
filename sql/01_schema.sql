-- =============================================================================
-- RetailPulse 360 — schema, constraints and relationships (PostgreSQL 13+)
-- Synthetic portfolio data: fictional company, synthetic customers and churn label.
--
-- Run from the repository root:
--   psql -d retailpulse360 -v ON_ERROR_STOP=1 -f sql/01_schema.sql
-- All objects live in the "retailpulse" schema. Re-running drops and recreates it.
-- =============================================================================

SET client_min_messages = warning;
DROP SCHEMA IF EXISTS retailpulse CASCADE;
CREATE SCHEMA retailpulse;
SET search_path TO retailpulse;

CREATE TABLE customers (
    customer_id          VARCHAR(10) PRIMARY KEY,
    signup_date          DATE        NOT NULL,
    state                CHAR(2)     NOT NULL,
    region               VARCHAR(20) NOT NULL,
    acquisition_channel  VARCHAR(30) NOT NULL,
    preferred_device     VARCHAR(20) NOT NULL,
    loyalty_tier         VARCHAR(20) NOT NULL
        CHECK (loyalty_tier IN ('Bronze', 'Silver', 'Gold', 'Platinum'))
);

CREATE TABLE products (
    product_id      VARCHAR(10)   PRIMARY KEY,
    category        VARCHAR(40)   NOT NULL,
    subcategory     VARCHAR(40)   NOT NULL,
    base_price_usd  NUMERIC(10,2) NOT NULL CHECK (base_price_usd > 0),
    unit_cost_usd   NUMERIC(10,2) NOT NULL CHECK (unit_cost_usd >= 0)
);

CREATE TABLE orders (
    order_id                     VARCHAR(12)   PRIMARY KEY,
    customer_id                  VARCHAR(10)   NOT NULL REFERENCES customers (customer_id),
    order_date                   DATE          NOT NULL,
    sales_channel                VARCHAR(30)   NOT NULL,
    payment_method               VARCHAR(30)   NOT NULL,
    shipping_type                VARCHAR(30)   NOT NULL,
    coupon_used                  SMALLINT      NOT NULL CHECK (coupon_used IN (0, 1)),
    discount_pct                 NUMERIC(6,2)  NOT NULL CHECK (discount_pct BETWEEN 0 AND 100),
    order_status                 VARCHAR(20)   NOT NULL CHECK (order_status IN ('Completed', 'Refunded', 'Cancelled')),
    shipping_fee_usd             NUMERIC(10,2) NOT NULL CHECK (shipping_fee_usd >= 0),
    tax_amount_usd               NUMERIC(10,2) NOT NULL CHECK (tax_amount_usd >= 0),
    gross_merchandise_value_usd  NUMERIC(12,2) NOT NULL CHECK (gross_merchandise_value_usd >= 0),
    net_revenue_usd              NUMERIC(12,2) NOT NULL CHECK (net_revenue_usd >= 0),
    total_cost_usd               NUMERIC(12,2) NOT NULL CHECK (total_cost_usd >= 0),
    profit_usd                   NUMERIC(12,2) NOT NULL
);

CREATE TABLE order_items (
    order_item_id     VARCHAR(16)   PRIMARY KEY,
    order_id          VARCHAR(12)   NOT NULL REFERENCES orders (order_id),
    product_id        VARCHAR(10)   NOT NULL REFERENCES products (product_id),
    quantity          INTEGER       NOT NULL CHECK (quantity > 0),
    unit_price_usd    NUMERIC(10,2) NOT NULL CHECK (unit_price_usd >= 0),
    discount_pct      NUMERIC(6,2)  NOT NULL CHECK (discount_pct BETWEEN 0 AND 100),
    line_revenue_usd  NUMERIC(12,2) NOT NULL CHECK (line_revenue_usd >= 0),
    line_cost_usd     NUMERIC(12,2) NOT NULL CHECK (line_cost_usd >= 0)
);

CREATE TABLE web_sessions (
    session_id        VARCHAR(16)   PRIMARY KEY,
    customer_id       VARCHAR(10)   NOT NULL REFERENCES customers (customer_id),
    session_date      DATE          NOT NULL,
    device            VARCHAR(20)   NOT NULL,
    traffic_source    VARCHAR(30)   NOT NULL,
    pages_viewed      INTEGER       NOT NULL CHECK (pages_viewed >= 0),
    session_minutes   NUMERIC(10,2) NOT NULL CHECK (session_minutes >= 0),
    product_views     INTEGER       NOT NULL CHECK (product_views >= 0),
    cart_adds         INTEGER       NOT NULL CHECK (cart_adds >= 0),
    checkout_started  SMALLINT      NOT NULL CHECK (checkout_started IN (0, 1)),
    converted         SMALLINT      NOT NULL CHECK (converted IN (0, 1))
);

CREATE TABLE support_tickets (
    ticket_id         VARCHAR(16)   PRIMARY KEY,
    customer_id       VARCHAR(10)   NOT NULL REFERENCES customers (customer_id),
    opened_date       DATE          NOT NULL,
    issue_type        VARCHAR(40)   NOT NULL,
    priority          VARCHAR(20)   NOT NULL CHECK (priority IN ('Low', 'Medium', 'High')),
    resolution_hours  NUMERIC(10,2) NOT NULL CHECK (resolution_hours > 0),
    csat_score        SMALLINT      NOT NULL CHECK (csat_score BETWEEN 1 AND 5),
    refunded          SMALLINT      NOT NULL CHECK (refunded IN (0, 1))
);

-- One row per month and channel: (month, channel) is the natural key.
CREATE TABLE marketing_spend (
    month        DATE          NOT NULL,
    channel      VARCHAR(30)   NOT NULL,
    spend_usd    NUMERIC(12,2) NOT NULL CHECK (spend_usd >= 0),
    impressions  INTEGER       NOT NULL CHECK (impressions >= 0),
    clicks       INTEGER       NOT NULL CHECK (clicks >= 0),
    leads        INTEGER       NOT NULL CHECK (leads >= 0),
    PRIMARY KEY (month, channel)
);

-- Prepared customer-level modeling table (snapshot 2026-05-31).
CREATE TABLE customer_modeling_snapshot (
    customer_id               VARCHAR(10) PRIMARY KEY REFERENCES customers (customer_id),
    snapshot_date             DATE        NOT NULL,
    region                    VARCHAR(20) NOT NULL,
    acquisition_channel       VARCHAR(30) NOT NULL,
    preferred_device          VARCHAR(20) NOT NULL,
    loyalty_tier              VARCHAR(20) NOT NULL,
    days_since_signup         INTEGER     NOT NULL,
    recency_days              NUMERIC(10,2),
    frequency_12m             NUMERIC(10,2),
    monetary_value_12m        NUMERIC(12,2),
    avg_order_value_12m       NUMERIC(12,4),
    profit_12m                NUMERIC(12,2),
    gross_margin_pct_12m      NUMERIC(10,6),
    avg_discount_pct_12m      NUMERIC(10,6),
    refund_rate_12m           NUMERIC(10,6),
    category_diversity_12m    NUMERIC(10,2),
    web_sessions_90d          NUMERIC(10,2),
    avg_session_minutes_90d   NUMERIC(10,4),
    product_views_90d         NUMERIC(10,2),
    cart_adds_90d             NUMERIC(10,2),
    conversion_rate_90d       NUMERIC(10,6),
    cart_add_rate_90d         NUMERIC(10,6),
    support_tickets_12m       NUMERIC(10,2),
    avg_resolution_hours_12m  NUMERIC(10,4),
    avg_csat_12m              NUMERIC(10,4),
    refund_requests_12m       NUMERIC(10,2),
    churned_next_90d          SMALLINT    NOT NULL CHECK (churned_next_90d IN (0, 1))
);

-- Indexes on foreign keys and dates used by the analysis queries.
CREATE INDEX idx_orders_customer      ON orders (customer_id);
CREATE INDEX idx_orders_date          ON orders (order_date);
CREATE INDEX idx_order_items_order    ON order_items (order_id);
CREATE INDEX idx_order_items_product  ON order_items (product_id);
CREATE INDEX idx_sessions_customer    ON web_sessions (customer_id, session_date);
CREATE INDEX idx_tickets_customer     ON support_tickets (customer_id, opened_date);
