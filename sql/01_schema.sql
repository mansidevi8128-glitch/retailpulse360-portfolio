-- RetailPulse 360 starter schema (PostgreSQL-style data types)
CREATE TABLE customers (
  customer_id VARCHAR(10) PRIMARY KEY,
  signup_date DATE,
  state VARCHAR(2),
  region VARCHAR(20),
  acquisition_channel VARCHAR(30),
  preferred_device VARCHAR(20),
  loyalty_tier VARCHAR(20)
);

CREATE TABLE products (
  product_id VARCHAR(10) PRIMARY KEY,
  category VARCHAR(40),
  subcategory VARCHAR(40),
  base_price_usd NUMERIC(10,2),
  unit_cost_usd NUMERIC(10,2)
);

CREATE TABLE orders (
  order_id VARCHAR(12) PRIMARY KEY,
  customer_id VARCHAR(10),
  order_date DATE,
  sales_channel VARCHAR(30),
  payment_method VARCHAR(30),
  shipping_type VARCHAR(30),
  coupon_used INTEGER,
  discount_pct NUMERIC(6,2),
  order_status VARCHAR(20),
  shipping_fee_usd NUMERIC(10,2),
  tax_amount_usd NUMERIC(10,2),
  gross_merchandise_value_usd NUMERIC(12,2),
  net_revenue_usd NUMERIC(12,2),
  total_cost_usd NUMERIC(12,2),
  profit_usd NUMERIC(12,2)
);

CREATE TABLE order_items (
  order_item_id VARCHAR(16) PRIMARY KEY,
  order_id VARCHAR(12),
  product_id VARCHAR(10),
  quantity INTEGER,
  unit_price_usd NUMERIC(10,2),
  discount_pct NUMERIC(6,2),
  line_revenue_usd NUMERIC(12,2),
  line_cost_usd NUMERIC(12,2)
);

CREATE TABLE web_sessions (
  session_id VARCHAR(16) PRIMARY KEY,
  customer_id VARCHAR(10),
  session_date DATE,
  device VARCHAR(20),
  traffic_source VARCHAR(30),
  pages_viewed INTEGER,
  session_minutes NUMERIC(10,2),
  product_views INTEGER,
  cart_adds INTEGER,
  checkout_started INTEGER,
  converted INTEGER
);

CREATE TABLE support_tickets (
  ticket_id VARCHAR(16) PRIMARY KEY,
  customer_id VARCHAR(10),
  opened_date DATE,
  issue_type VARCHAR(40),
  priority VARCHAR(20),
  resolution_hours NUMERIC(10,2),
  csat_score INTEGER,
  refunded INTEGER
);

CREATE TABLE marketing_spend (
  month DATE,
  channel VARCHAR(30),
  spend_usd NUMERIC(12,2),
  impressions INTEGER,
  clicks INTEGER,
  leads INTEGER
);
