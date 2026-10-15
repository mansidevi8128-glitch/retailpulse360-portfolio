"""Customer-level feature engineering at the snapshot date.

``build_customer_features`` rebuilds the provided modeling snapshot from the
raw tables using only events on or before the snapshot date. Matching the
provided file proves its features contain no post-snapshot information.

The audit found one synthetic artifact: in the provided snapshot,
``recency_days`` is set to ``days_since_signup + 30`` for every customer with
no completed order in the 12-month window - even customers who bought earlier.
``add_corrected_features`` adds a true recency measure and an explicit flag so
models do not depend on that encoding.
"""

import numpy as np
import pandas as pd

from .config import SNAPSHOT_DATE, STATUS_COMPLETED, STATUS_REFUNDED

ID_COLUMN = "customer_id"
TARGET = "churned_next_90d"
NON_FEATURE_COLUMNS = {ID_COLUMN, TARGET, "snapshot_date"}

CATEGORICAL_FEATURES = ["region", "acquisition_channel", "preferred_device", "loyalty_tier"]

SNAPSHOT_NUMERIC_FEATURES = [
    "days_since_signup",
    "recency_days",
    "frequency_12m",
    "monetary_value_12m",
    "avg_order_value_12m",
    "profit_12m",
    "gross_margin_pct_12m",
    "avg_discount_pct_12m",
    "refund_rate_12m",
    "category_diversity_12m",
    "web_sessions_90d",
    "avg_session_minutes_90d",
    "product_views_90d",
    "cart_adds_90d",
    "conversion_rate_90d",
    "cart_add_rate_90d",
    "support_tickets_12m",
    "avg_resolution_hours_12m",
    "avg_csat_12m",
    "refund_requests_12m",
]

# Model features: the snapshot recency sentinel is replaced by true recency
# plus explicit "no purchase" flags.
MODEL_NUMERIC_FEATURES = [
    "days_since_signup",
    "days_since_last_purchase",
    "never_purchased",
    "no_purchase_12m",
    "frequency_12m",
    "monetary_value_12m",
    "avg_order_value_12m",
    "profit_12m",
    "gross_margin_pct_12m",
    "avg_discount_pct_12m",
    "refund_rate_12m",
    "category_diversity_12m",
    "web_sessions_90d",
    "avg_session_minutes_90d",
    "product_views_90d",
    "cart_adds_90d",
    "conversion_rate_90d",
    "cart_add_rate_90d",
    "support_tickets_12m",
    "avg_resolution_hours_12m",
    "avg_csat_12m",
    "refund_requests_12m",
]

NO_TICKET_CSAT_FILL = 4.0  # value the provided snapshot uses when a customer has no tickets


def _window(df: pd.DataFrame, date_col: str, snapshot_date: pd.Timestamp, days: int) -> pd.DataFrame:
    """Rows dated within [snapshot - days, snapshot] (both ends inclusive)."""
    start = snapshot_date - pd.Timedelta(days=days)
    return df[(df[date_col] >= start) & (df[date_col] <= snapshot_date)]


def build_customer_features(tables: dict[str, pd.DataFrame], snapshot_date: pd.Timestamp = SNAPSHOT_DATE) -> pd.DataFrame:
    """Rebuild the customer modeling snapshot (minus the target) from raw tables."""
    customers = tables["customers"]
    orders = tables["orders"]
    order_items = tables["order_items"]
    products = tables["products"]
    sessions = tables["web_sessions"]
    tickets = tables["support_tickets"]

    base = customers[customers["signup_date"] <= snapshot_date].set_index(ID_COLUMN)
    features = base[CATEGORICAL_FEATURES].copy()
    features.insert(0, "snapshot_date", snapshot_date)
    features["days_since_signup"] = (snapshot_date - base["signup_date"]).dt.days

    # Orders: 12-month window ending at the snapshot.
    orders_12m = _window(orders, "order_date", snapshot_date, 365)
    completed_12m = orders_12m[orders_12m["order_status"] == STATUS_COMPLETED]
    order_agg = completed_12m.groupby(ID_COLUMN).agg(
        last_order_12m=("order_date", "max"),
        frequency_12m=("order_id", "size"),
        monetary_value_12m=("net_revenue_usd", "sum"),
        profit_12m=("profit_usd", "sum"),
        avg_discount_pct_12m=("discount_pct", "mean"),
    )
    features = features.join(order_agg)
    has_12m = features["frequency_12m"].notna()
    features["recency_days"] = np.where(
        has_12m,
        (snapshot_date - features["last_order_12m"]).dt.days,
        features["days_since_signup"] + 30,
    )
    features = features.drop(columns="last_order_12m")
    features[["frequency_12m", "monetary_value_12m", "profit_12m", "avg_discount_pct_12m"]] = features[
        ["frequency_12m", "monetary_value_12m", "profit_12m", "avg_discount_pct_12m"]
    ].fillna(0.0)
    features["avg_order_value_12m"] = (features["monetary_value_12m"] / features["frequency_12m"].replace(0, np.nan)).fillna(0.0)
    features["gross_margin_pct_12m"] = (features["profit_12m"] / features["monetary_value_12m"].replace(0, np.nan)).fillna(0.0)

    refund_flags = orders_12m.assign(is_refunded=(orders_12m["order_status"] == STATUS_REFUNDED).astype(float))
    features["refund_rate_12m"] = refund_flags.groupby(ID_COLUMN)["is_refunded"].mean().reindex(features.index).fillna(0.0)

    lines = order_items.merge(completed_12m[["order_id", ID_COLUMN]], on="order_id", how="inner").merge(products[["product_id", "category"]], on="product_id")
    features["category_diversity_12m"] = lines.groupby(ID_COLUMN)["category"].nunique().reindex(features.index).fillna(0).astype(float)

    # Web sessions: 90-day window.
    sessions_90d = _window(sessions, "session_date", snapshot_date, 90)
    web = sessions_90d.groupby(ID_COLUMN).agg(
        web_sessions_90d=("session_id", "size"),
        avg_session_minutes_90d=("session_minutes", "mean"),
        product_views_90d=("product_views", "sum"),
        cart_adds_90d=("cart_adds", "sum"),
        conversions_90d=("converted", "sum"),
    )
    features = features.join(web)
    web_cols = ["web_sessions_90d", "avg_session_minutes_90d", "product_views_90d", "cart_adds_90d", "conversions_90d"]
    features[web_cols] = features[web_cols].fillna(0.0)
    features["conversion_rate_90d"] = (features["conversions_90d"] / features["web_sessions_90d"].replace(0, np.nan)).fillna(0.0)
    features["cart_add_rate_90d"] = (features["cart_adds_90d"] / features["product_views_90d"].replace(0, np.nan)).fillna(0.0)
    features = features.drop(columns="conversions_90d")

    # Support tickets: 12-month window.
    tickets_12m = _window(tickets, "opened_date", snapshot_date, 365)
    support = tickets_12m.groupby(ID_COLUMN).agg(
        support_tickets_12m=("ticket_id", "size"),
        avg_resolution_hours_12m=("resolution_hours", "mean"),
        avg_csat_12m=("csat_score", "mean"),
        refund_requests_12m=("refunded", "sum"),
    )
    features = features.join(support)
    features["support_tickets_12m"] = features["support_tickets_12m"].fillna(0.0)
    features["avg_resolution_hours_12m"] = features["avg_resolution_hours_12m"].fillna(0.0)
    features["avg_csat_12m"] = features["avg_csat_12m"].fillna(NO_TICKET_CSAT_FILL)
    features["refund_requests_12m"] = features["refund_requests_12m"].fillna(0.0)

    return features.reset_index()


def add_corrected_features(snapshot: pd.DataFrame, orders: pd.DataFrame, snapshot_date: pd.Timestamp = SNAPSHOT_DATE) -> pd.DataFrame:
    """Add true recency and explicit purchase flags using orders up to the snapshot.

    * days_since_last_purchase - days since the last completed order in all
      observed history; for customers who never purchased, days since signup.
    * never_purchased          - 1 if no completed order was ever observed.
    * no_purchase_12m          - 1 if no completed order in the 12-month window.
    """
    history = orders[(orders["order_status"] == STATUS_COMPLETED) & (orders["order_date"] <= snapshot_date)]
    last_purchase = history.groupby(ID_COLUMN)["order_date"].max()
    out = snapshot.copy()
    last = out[ID_COLUMN].map(last_purchase)
    out["never_purchased"] = last.isna().astype(int)
    out["days_since_last_purchase"] = np.where(last.isna(), out["days_since_signup"], (snapshot_date - last).dt.days)
    out["no_purchase_12m"] = (out["frequency_12m"] == 0).astype(int)
    return out


def assert_no_leakage(feature_columns: list[str]) -> None:
    """Raise if an identifier, the target or the snapshot date is used as a feature."""
    forbidden = NON_FEATURE_COLUMNS.intersection(feature_columns)
    if forbidden:
        raise ValueError(f"Leakage risk - non-feature columns used as predictors: {sorted(forbidden)}")
