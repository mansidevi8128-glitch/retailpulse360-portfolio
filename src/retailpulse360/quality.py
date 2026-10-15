"""Reusable data-quality checks.

Each check returns a tidy DataFrame so results can be shown in notebooks,
written to reports, and asserted in tests.
"""

import numpy as np
import pandas as pd

from .config import FOREIGN_KEYS, RAW_TABLES, SNAPSHOT_DATE, STATUS_CANCELLED, STATUS_COMPLETED, STATUS_REFUNDED

MONEY_TOLERANCE = 0.01  # one cent


def profile_table(name: str, df: pd.DataFrame) -> pd.DataFrame:
    """Column-level profile: dtype, missing values, distinct values, min/max."""
    rows = []
    for column in df.columns:
        series = df[column]
        is_orderable = pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series)
        rows.append(
            {
                "table": name,
                "column": column,
                "dtype": str(series.dtype),
                "missing": int(series.isna().sum()),
                "distinct": int(series.nunique()),
                "min": series.min() if is_orderable else None,
                "max": series.max() if is_orderable else None,
            }
        )
    return pd.DataFrame(rows)


def table_overview(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Row/column counts, missing cells and exact duplicate rows per table."""
    rows = []
    for name, df in tables.items():
        date_cols = RAW_TABLES[name][2] if name in RAW_TABLES else []
        date_range = ""
        if date_cols:
            col = date_cols[0]
            date_range = f"{df[col].min():%Y-%m-%d} to {df[col].max():%Y-%m-%d}"
        rows.append(
            {
                "table": name,
                "rows": len(df),
                "columns": df.shape[1],
                "missing_cells": int(df.isna().sum().sum()),
                "duplicate_rows": int(df.duplicated().sum()),
                "date_range": date_range,
            }
        )
    return pd.DataFrame(rows)


def check_primary_key(df: pd.DataFrame, key) -> dict:
    """Count null and duplicated values of a (possibly composite) primary key."""
    key_cols = [key] if isinstance(key, str) else list(key)
    nulls = int(df[key_cols].isna().any(axis=1).sum())
    duplicates = int(df.duplicated(subset=key_cols).sum())
    return {"key": " + ".join(key_cols), "null_keys": nulls, "duplicate_keys": duplicates, "passed": nulls == 0 and duplicates == 0}


def check_primary_keys(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, (_, key, _) in RAW_TABLES.items():
        rows.append({"table": name, **check_primary_key(tables[name], key)})
    return pd.DataFrame(rows)


def check_foreign_key(child: pd.DataFrame, child_col: str, parent: pd.DataFrame, parent_col: str) -> int:
    """Number of child rows whose key does not exist in the parent table."""
    return int((~child[child_col].isin(parent[parent_col])).sum())


def check_foreign_keys(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for child, child_col, parent, parent_col in FOREIGN_KEYS:
        orphans = check_foreign_key(tables[child], child_col, tables[parent], parent_col)
        rows.append(
            {
                "relationship": f"{child}.{child_col} -> {parent}.{parent_col}",
                "orphan_rows": orphans,
                "passed": orphans == 0,
            }
        )
    return pd.DataFrame(rows)


def order_item_totals(order_items: pd.DataFrame) -> pd.DataFrame:
    """Aggregate line items to order grain (avoids join fan-out)."""
    return order_items.groupby("order_id", as_index=False).agg(
        item_lines=("order_item_id", "size"),
        units=("quantity", "sum"),
        line_revenue_usd=("line_revenue_usd", "sum"),
        line_cost_usd=("line_cost_usd", "sum"),
        min_line_discount_pct=("discount_pct", "min"),
        max_line_discount_pct=("discount_pct", "max"),
    )


def reconcile_order_financials(orders: pd.DataFrame, order_items: pd.DataFrame) -> pd.DataFrame:
    """Test how order-header money fields relate to line items, by status.

    Returns one row per (status, rule) with the number of orders violating it.
    """
    merged = orders.merge(order_item_totals(order_items), on="order_id", how="left")
    is_completed = merged["order_status"] == STATUS_COMPLETED
    is_refunded = merged["order_status"] == STATUS_REFUNDED
    is_cancelled = merged["order_status"] == STATUS_CANCELLED

    def off(a, b):
        return (a - b).abs() > MONEY_TOLERANCE

    rules = [
        ("All", "GMV = sum of line revenue (post-discount)", off(merged["gross_merchandise_value_usd"], merged["line_revenue_usd"])),
        ("All", "Profit = net revenue - total cost", off(merged["profit_usd"], merged["net_revenue_usd"] - merged["total_cost_usd"])),
        ("All", "Order discount = every line discount", (merged["discount_pct"] != merged["min_line_discount_pct"]) | (merged["discount_pct"] != merged["max_line_discount_pct"])),
        ("Completed", "Net revenue = GMV + shipping fee (tax excluded)", is_completed & off(merged["net_revenue_usd"], merged["gross_merchandise_value_usd"] + merged["shipping_fee_usd"])),
        ("Completed", "Total cost = sum of line cost", is_completed & off(merged["total_cost_usd"], merged["line_cost_usd"])),
        ("Refunded", "Net revenue = 0", is_refunded & (merged["net_revenue_usd"] != 0)),
        ("Refunded", "Total cost = sum of line cost (goods not recovered)", is_refunded & off(merged["total_cost_usd"], merged["line_cost_usd"])),
        ("Cancelled", "Net revenue, cost and profit = 0", is_cancelled & ((merged["net_revenue_usd"] != 0) | (merged["total_cost_usd"] != 0) | (merged["profit_usd"] != 0))),
    ]
    status_counts = merged["order_status"].value_counts()
    rows = []
    for scope, rule, violated in rules:
        checked = len(merged) if scope == "All" else int(status_counts.get(scope, 0))
        rows.append({"scope": scope, "rule": rule, "orders_checked": checked, "violations": int(violated.sum())})
    return pd.DataFrame(rows)


def business_rule_checks(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Domain validity checks. A non-zero count is a finding, not always an error."""
    customers = tables["customers"]
    products = tables["products"]
    orders = tables["orders"]
    items = tables["order_items"]
    sessions = tables["web_sessions"]
    tickets = tables["support_tickets"]
    marketing = tables["marketing_spend"]

    signup = customers.set_index("customer_id")["signup_date"]
    line_check = items["quantity"] * items["unit_price_usd"] * (1 - items["discount_pct"] / 100)
    item_products = items.merge(products, on="product_id", how="left")

    checks = [
        ("customers", "Signup date after snapshot date", (customers["signup_date"] > SNAPSHOT_DATE).sum()),
        ("customers", "State mapped to more than one region", (customers.groupby("state")["region"].nunique() > 1).sum()),
        ("products", "Unit cost >= base price (non-positive margin)", (products["unit_cost_usd"] >= products["base_price_usd"]).sum()),
        ("orders", "Order dated before customer signup", (orders["order_date"] < orders["customer_id"].map(signup)).sum()),
        ("orders", "Order dated after snapshot date", (orders["order_date"] > SNAPSHOT_DATE).sum()),
        ("orders", "Negative money value", (orders[["shipping_fee_usd", "tax_amount_usd", "gross_merchandise_value_usd", "net_revenue_usd", "total_cost_usd"]] < 0).any(axis=1).sum()),
        ("orders", "Discount outside 0-100%", (~orders["discount_pct"].between(0, 100)).sum()),
        ("orders", "coupon_used = 1 but discount_pct = 0", ((orders["coupon_used"] == 1) & (orders["discount_pct"] == 0)).sum()),
        ("orders", "coupon_used = 0 but discount_pct > 0", ((orders["coupon_used"] == 0) & (orders["discount_pct"] > 0)).sum()),
        ("orders", "Completed order with negative profit", ((orders["order_status"] == STATUS_COMPLETED) & (orders["profit_usd"] < 0)).sum()),
        ("orders", "Order without line items", (~orders["order_id"].isin(items["order_id"])).sum()),
        ("order_items", "Quantity < 1", (items["quantity"] < 1).sum()),
        ("order_items", "Line revenue != qty x price x (1 - discount) (> 1 cent)", ((line_check - items["line_revenue_usd"]).abs() > MONEY_TOLERANCE).sum()),
        ("order_items", "Line cost != qty x product unit cost (> 1 cent)", ((item_products["quantity"] * item_products["unit_cost_usd"] - item_products["line_cost_usd"]).abs() > MONEY_TOLERANCE).sum()),
        ("web_sessions", "Session dated before customer signup", (sessions["session_date"] < sessions["customer_id"].map(signup)).sum()),
        ("web_sessions", "Converted without checkout started", ((sessions["converted"] == 1) & (sessions["checkout_started"] == 0)).sum()),
        ("web_sessions", "Checkout started without a cart add", ((sessions["checkout_started"] == 1) & (sessions["cart_adds"] == 0)).sum()),
        ("web_sessions", "Cart adds > product views", (sessions["cart_adds"] > sessions["product_views"]).sum()),
        ("support_tickets", "Ticket opened before customer signup", (tickets["opened_date"] < tickets["customer_id"].map(signup)).sum()),
        ("support_tickets", "CSAT outside 1-5", (~tickets["csat_score"].between(1, 5)).sum()),
        ("support_tickets", "Non-positive resolution hours", (tickets["resolution_hours"] <= 0).sum()),
        ("marketing_spend", "Clicks > impressions", (marketing["clicks"] > marketing["impressions"]).sum()),
        ("marketing_spend", "Leads > clicks", (marketing["leads"] > marketing["clicks"]).sum()),
    ]
    return pd.DataFrame(
        [{"table": table, "check": check, "rows_flagged": int(count)} for table, check, count in checks]
    )


def iqr_outliers(series: pd.Series, multiplier: float = 3.0) -> dict:
    """Count values outside [Q1 - k*IQR, Q3 + k*IQR] (k=3 flags extreme values only)."""
    q1, q3 = series.quantile([0.25, 0.75])
    iqr = q3 - q1
    low, high = q1 - multiplier * iqr, q3 + multiplier * iqr
    return {
        "lower_fence": round(float(low), 2),
        "upper_fence": round(float(high), 2),
        "outliers": int(((series < low) | (series > high)).sum()),
        "max": round(float(series.max()), 2),
    }


def outlier_summary(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    columns = [
        ("orders", "gross_merchandise_value_usd"),
        ("orders", "profit_usd"),
        ("order_items", "unit_price_usd"),
        ("web_sessions", "session_minutes"),
        ("web_sessions", "pages_viewed"),
        ("support_tickets", "resolution_hours"),
        ("marketing_spend", "spend_usd"),
    ]
    return pd.DataFrame(
        [{"table": t, "column": c, **iqr_outliers(tables[t][c])} for t, c in columns]
    )


def snapshot_reproduction_check(snapshot: pd.DataFrame, rebuilt: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Share of customers whose snapshot value equals the value rebuilt from raw data."""
    left = snapshot.set_index("customer_id").sort_index()
    right = rebuilt.set_index("customer_id").reindex(left.index)
    rows = []
    for column in columns:
        matches = np.isclose(left[column].astype(float), right[column].astype(float), atol=MONEY_TOLERANCE, equal_nan=True)
        rows.append({"feature": column, "match_rate": float(matches.mean()), "mismatches": int((~matches).sum())})
    return pd.DataFrame(rows)
