"""Business KPI calculations.

Metric definitions (full detail in docs/metric_definitions.md):

* Net revenue  = ``net_revenue_usd`` = merchandise value after discounts + shipping
  fee, excluding sales tax. Only Completed orders carry net revenue.
* GMV          = ``gross_merchandise_value_usd`` = post-discount merchandise value
  of every *placed* order (any status), excluding shipping and tax. It measures
  demand, not earned revenue.
* Profit       = ``profit_usd`` = net revenue - merchandise cost. Refunded orders
  carry a loss equal to their merchandise cost; cancelled orders are zero. No
  shipping, payment, support or marketing costs exist in the data, so this is a
  product-level contribution, not net income.
* AOV          = net revenue / completed orders.
* Refund rate  = refunded orders / (completed + refunded orders), i.e. of orders
  that were fulfilled, the share that were refunded. Cancelled orders are excluded.
"""

import numpy as np
import pandas as pd

from .config import SNAPSHOT_DATE, STATUS_CANCELLED, STATUS_COMPLETED, STATUS_REFUNDED


def safe_divide(numerator, denominator):
    """Element-wise division that returns NaN instead of inf when dividing by zero."""
    numerator = pd.Series(numerator) if np.isscalar(numerator) else numerator
    if np.isscalar(denominator):
        return np.nan if denominator == 0 else numerator / denominator
    return numerator / denominator.replace(0, np.nan)


def ratio(numerator: float, denominator: float) -> float:
    return float("nan") if denominator == 0 else float(numerator) / float(denominator)


def prepare_orders(orders: pd.DataFrame) -> pd.DataFrame:
    """Add month and status flags used by every KPI."""
    out = orders.copy()
    out["order_month"] = out["order_date"].dt.to_period("M").dt.to_timestamp()
    out["is_completed"] = (out["order_status"] == STATUS_COMPLETED).astype(int)
    out["is_refunded"] = (out["order_status"] == STATUS_REFUNDED).astype(int)
    out["is_cancelled"] = (out["order_status"] == STATUS_CANCELLED).astype(int)
    out["is_fulfilled"] = out["is_completed"] + out["is_refunded"]
    return out


def _order_kpis(grouped) -> pd.DataFrame:
    """Shared aggregation for any order-level grouping."""
    kpis = grouped.agg(
        orders_placed=("order_id", "size"),
        completed_orders=("is_completed", "sum"),
        refunded_orders=("is_refunded", "sum"),
        cancelled_orders=("is_cancelled", "sum"),
        gmv_usd=("gross_merchandise_value_usd", "sum"),
        net_revenue_usd=("net_revenue_usd", "sum"),
        profit_usd=("profit_usd", "sum"),
    )
    kpis["aov_usd"] = safe_divide(kpis["net_revenue_usd"], kpis["completed_orders"])
    kpis["profit_margin_pct"] = 100 * safe_divide(kpis["profit_usd"], kpis["net_revenue_usd"])
    kpis["refund_rate_pct"] = 100 * safe_divide(kpis["refunded_orders"], kpis["completed_orders"] + kpis["refunded_orders"])
    kpis["cancellation_rate_pct"] = 100 * safe_divide(kpis["cancelled_orders"], kpis["orders_placed"])
    return kpis


def executive_summary(orders: pd.DataFrame, customers: pd.DataFrame) -> dict:
    """Headline KPIs for the full observed period."""
    o = prepare_orders(orders)
    completed = o[o["is_completed"] == 1]
    return {
        "period_start": o["order_date"].min().strftime("%Y-%m-%d"),
        "period_end": o["order_date"].max().strftime("%Y-%m-%d"),
        "customers": int(customers["customer_id"].nunique()),
        "purchasing_customers": int(completed["customer_id"].nunique()),
        "orders_placed": int(len(o)),
        "completed_orders": int(o["is_completed"].sum()),
        "refunded_orders": int(o["is_refunded"].sum()),
        "cancelled_orders": int(o["is_cancelled"].sum()),
        "gmv_usd": float(o["gross_merchandise_value_usd"].sum()),
        "net_revenue_usd": float(o["net_revenue_usd"].sum()),
        "shipping_revenue_usd": float(completed["shipping_fee_usd"].sum()),
        "profit_usd": float(o["profit_usd"].sum()),
        "refund_loss_usd": float(-o.loc[o["is_refunded"] == 1, "profit_usd"].sum()),
        "aov_usd": ratio(o["net_revenue_usd"].sum(), o["is_completed"].sum()),
        "profit_margin_pct": 100 * ratio(o["profit_usd"].sum(), o["net_revenue_usd"].sum()),
        "refund_rate_pct": 100 * ratio(o["is_refunded"].sum(), o["is_fulfilled"].sum()),
        "cancellation_rate_pct": 100 * ratio(o["is_cancelled"].sum(), len(o)),
    }


def monthly_kpis(orders: pd.DataFrame) -> pd.DataFrame:
    """Monthly revenue, profit, orders, active customers, AOV and MoM growth."""
    o = prepare_orders(orders)
    kpis = _order_kpis(o.groupby("order_month"))
    active = o[o["is_completed"] == 1].groupby("order_month")["customer_id"].nunique()
    kpis["active_customers"] = active.reindex(kpis.index).fillna(0).astype(int)
    kpis["revenue_mom_pct"] = 100 * kpis["net_revenue_usd"].pct_change()
    kpis["profit_mom_pct"] = 100 * kpis["profit_usd"].pct_change()
    kpis["orders_mom_pct"] = 100 * kpis["completed_orders"].pct_change()
    kpis["revenue_yoy_pct"] = 100 * kpis["net_revenue_usd"].pct_change(12)
    return kpis.reset_index()


def yearly_kpis(orders: pd.DataFrame, through_month: int = 5) -> pd.DataFrame:
    """Year-to-date KPIs for the same calendar months in each year.

    2026 data ends in May, so comparing Jan-May across years avoids comparing a
    partial year to full years.
    """
    o = prepare_orders(orders)
    o = o[o["order_date"].dt.month <= through_month]
    kpis = _order_kpis(o.groupby(o["order_date"].dt.year.rename("year")))
    kpis["active_customers"] = o[o["is_completed"] == 1].groupby(o["order_date"].dt.year)["customer_id"].nunique()
    return kpis.reset_index()


def category_performance(orders: pd.DataFrame, order_items: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """Product-category revenue and profit computed at line-item grain.

    Order status is brought down to the line (many-to-one join, so there is no
    fan-out). Category revenue excludes shipping fees, so the categories sum to
    net revenue minus shipping revenue.
    """
    lines = order_items.merge(orders[["order_id", "order_status"]], on="order_id", how="left")
    lines = lines.merge(products[["product_id", "category"]], on="product_id", how="left")
    completed = lines["order_status"] == STATUS_COMPLETED
    refunded = lines["order_status"] == STATUS_REFUNDED
    lines["revenue_usd"] = np.where(completed, lines["line_revenue_usd"], 0.0)
    lines["cost_usd"] = np.where(completed | refunded, lines["line_cost_usd"], 0.0)
    lines["refund_loss_usd"] = np.where(refunded, lines["line_cost_usd"], 0.0)
    lines["units_sold"] = np.where(completed, lines["quantity"], 0)
    lines["is_completed_line"] = completed.astype(int)
    lines["is_refunded_line"] = refunded.astype(int)

    result = lines.groupby("category").agg(
        products=("product_id", "nunique"),
        units_sold=("units_sold", "sum"),
        revenue_usd=("revenue_usd", "sum"),
        cost_usd=("cost_usd", "sum"),
        refund_loss_usd=("refund_loss_usd", "sum"),
        completed_lines=("is_completed_line", "sum"),
        refunded_lines=("is_refunded_line", "sum"),
    )
    result["profit_usd"] = result["revenue_usd"] - result["cost_usd"]
    result["gross_margin_pct"] = 100 * safe_divide(result["profit_usd"], result["revenue_usd"])
    result["revenue_share_pct"] = 100 * result["revenue_usd"] / result["revenue_usd"].sum()
    result["profit_share_pct"] = 100 * result["profit_usd"] / result["profit_usd"].sum()
    result["line_refund_rate_pct"] = 100 * safe_divide(result["refunded_lines"], result["completed_lines"] + result["refunded_lines"])
    return result.sort_values("revenue_usd", ascending=False).reset_index()


def customer_dimension_performance(orders: pd.DataFrame, customers: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """KPIs by a customer attribute (region, acquisition_channel, loyalty_tier, ...)."""
    o = prepare_orders(orders).merge(customers[["customer_id", dimension]], on="customer_id", how="left")
    kpis = _order_kpis(o.groupby(dimension))
    kpis["customers"] = customers.groupby(dimension)["customer_id"].nunique()
    kpis["purchasing_customers"] = o[o["is_completed"] == 1].groupby(dimension)["customer_id"].nunique()
    kpis["revenue_per_customer_usd"] = safe_divide(kpis["net_revenue_usd"], kpis["customers"])
    kpis["revenue_share_pct"] = 100 * kpis["net_revenue_usd"] / kpis["net_revenue_usd"].sum()
    return kpis.sort_values("net_revenue_usd", ascending=False).reset_index()


def order_dimension_performance(orders: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """KPIs by an order attribute (sales_channel, payment_method, shipping_type, ...)."""
    o = prepare_orders(orders)
    kpis = _order_kpis(o.groupby(dimension))
    kpis["revenue_share_pct"] = 100 * kpis["net_revenue_usd"] / kpis["net_revenue_usd"].sum()
    return kpis.sort_values("net_revenue_usd", ascending=False).reset_index()


def discount_band_performance(orders: pd.DataFrame) -> pd.DataFrame:
    """Refund rate and margin by order discount level."""
    o = prepare_orders(orders)
    o["discount_band"] = pd.cut(o["discount_pct"], bins=[-0.01, 0, 10, 15, 20, 100], labels=["0%", "1-10%", "11-15%", "16-20%", "21%+"])
    return _order_kpis(o.groupby("discount_band", observed=True)).reset_index()


def first_year_value_by_channel(orders: pd.DataFrame, customers: pd.DataFrame, snapshot_date=SNAPSHOT_DATE) -> pd.DataFrame:
    """Net revenue and profit in each customer's first 365 days after signup.

    Only customers with a full 12 months observed inside the order history
    (signed up 2024-01-01 or later and at least 365 days before the snapshot)
    are included, so channels are compared on an equal time window.
    """
    order_start = orders["order_date"].min()
    eligible = customers[(customers["signup_date"] >= order_start) & (customers["signup_date"] <= snapshot_date - pd.Timedelta(days=365))]
    o = orders.merge(eligible[["customer_id", "signup_date", "acquisition_channel"]], on="customer_id", how="inner")
    o = o[o["order_date"] < o["signup_date"] + pd.Timedelta(days=365)]
    per_customer = o.groupby("customer_id").agg(net_revenue_usd=("net_revenue_usd", "sum"), profit_usd=("profit_usd", "sum"))
    per_customer = eligible.set_index("customer_id")[["acquisition_channel"]].join(per_customer).fillna({"net_revenue_usd": 0.0, "profit_usd": 0.0})
    result = per_customer.groupby("acquisition_channel").agg(
        cohort_customers=("net_revenue_usd", "size"),
        first_year_revenue_per_customer_usd=("net_revenue_usd", "mean"),
        first_year_profit_per_customer_usd=("profit_usd", "mean"),
        share_with_purchase_pct=("net_revenue_usd", lambda s: 100 * (s > 0).mean()),
    )
    return result.sort_values("first_year_profit_per_customer_usd", ascending=False).reset_index()


def marketing_efficiency(marketing: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """Channel spend efficiency: CTR, CPC, cost per lead and spend per new customer.

    "Spend per new customer" divides channel spend by customers whose
    acquisition_channel is that channel and who signed up inside the marketing
    period. This assumes the acquisition_channel attribution is correct; it is a
    blended ratio, not an incrementality measurement.
    """
    period_start = marketing["month"].min()
    period_end = marketing["month"].max() + pd.offsets.MonthEnd(0)
    new_customers = customers[customers["signup_date"].between(period_start, period_end)].groupby("acquisition_channel").size()
    result = marketing.groupby("channel").agg(
        spend_usd=("spend_usd", "sum"),
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        leads=("leads", "sum"),
    )
    result["ctr_pct"] = 100 * result["clicks"] / result["impressions"]
    result["cpc_usd"] = result["spend_usd"] / result["clicks"]
    result["click_to_lead_pct"] = 100 * result["leads"] / result["clicks"]
    result["cost_per_lead_usd"] = result["spend_usd"] / result["leads"]
    result["new_customers"] = new_customers.reindex(result.index).fillna(0).astype(int)
    result["spend_per_new_customer_usd"] = safe_divide(result["spend_usd"], result["new_customers"])
    result["spend_share_pct"] = 100 * result["spend_usd"] / result["spend_usd"].sum()
    return result.sort_values("spend_usd", ascending=False).reset_index().rename(columns={"channel": "acquisition_channel"})


def monthly_marketing(marketing: pd.DataFrame) -> pd.DataFrame:
    m = marketing.groupby("month").agg(spend_usd=("spend_usd", "sum"), clicks=("clicks", "sum"), leads=("leads", "sum"), impressions=("impressions", "sum"))
    m["cost_per_lead_usd"] = m["spend_usd"] / m["leads"]
    m["ctr_pct"] = 100 * m["clicks"] / m["impressions"]
    return m.reset_index()


def session_funnel(sessions: pd.DataFrame, by: str | None = None) -> pd.DataFrame:
    """Session-level funnel: sessions -> product view -> cart add -> checkout -> conversion."""
    s = sessions.assign(
        viewed_product=(sessions["product_views"] > 0).astype(int),
        added_to_cart=(sessions["cart_adds"] > 0).astype(int),
    )
    grouped = s.groupby(by) if by else s.groupby(lambda _: "All sessions")
    result = grouped.agg(
        sessions=("session_id", "size"),
        viewed_product=("viewed_product", "sum"),
        added_to_cart=("added_to_cart", "sum"),
        checkout_started=("checkout_started", "sum"),
        converted=("converted", "sum"),
        avg_session_minutes=("session_minutes", "mean"),
    )
    result["conversion_rate_pct"] = 100 * result["converted"] / result["sessions"]
    result["cart_rate_pct"] = 100 * result["added_to_cart"] / result["sessions"]
    result["checkout_completion_pct"] = 100 * safe_divide(result["converted"], result["checkout_started"])
    return result.sort_values("sessions", ascending=False).reset_index(names=by or "segment")


def support_summary(tickets: pd.DataFrame, by: str = "issue_type") -> pd.DataFrame:
    result = tickets.groupby(by).agg(
        tickets=("ticket_id", "size"),
        avg_resolution_hours=("resolution_hours", "mean"),
        median_resolution_hours=("resolution_hours", "median"),
        avg_csat=("csat_score", "mean"),
        satisfied_pct=("csat_score", lambda s: 100 * (s >= 4).mean()),
        refunded_pct=("refunded", lambda s: 100 * s.mean()),
    )
    result["ticket_share_pct"] = 100 * result["tickets"] / result["tickets"].sum()
    return result.sort_values("tickets", ascending=False).reset_index()


def resolution_time_vs_csat(tickets: pd.DataFrame) -> pd.DataFrame:
    bands = pd.cut(tickets["resolution_hours"], bins=[0, 8, 24, 48, 1000], labels=["<8h", "8-24h", "24-48h", "48h+"])
    return tickets.groupby(bands, observed=True).agg(
        tickets=("ticket_id", "size"),
        avg_csat=("csat_score", "mean"),
        satisfied_pct=("csat_score", lambda s: 100 * (s >= 4).mean()),
    ).reset_index(names="resolution_band")


def monthly_support_load(tickets: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    t = tickets.groupby(tickets["opened_date"].dt.to_period("M").dt.to_timestamp()).agg(tickets=("ticket_id", "size"), avg_csat=("csat_score", "mean"))
    completed = prepare_orders(orders).groupby("order_month")["is_fulfilled"].sum()
    t["tickets_per_100_orders"] = 100 * t["tickets"] / completed.reindex(t.index)
    return t.reset_index(names="month")


def purchase_frequency(orders: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """Distribution of completed orders per customer (all customers, incl. zero)."""
    counts = orders[orders["order_status"] == STATUS_COMPLETED].groupby("customer_id").size()
    counts = counts.reindex(customers["customer_id"], fill_value=0)
    bands = pd.cut(counts, bins=[-1, 0, 1, 2, 4, 9, 1000], labels=["0", "1", "2", "3-4", "5-9", "10+"])
    dist = bands.value_counts().sort_index().rename_axis("completed_orders").reset_index(name="customers")
    dist["share_pct"] = 100 * dist["customers"] / dist["customers"].sum()
    return dist


def repeat_purchase_rate(orders: pd.DataFrame) -> float:
    """Share of purchasing customers with 2+ completed orders (percent)."""
    counts = orders[orders["order_status"] == STATUS_COMPLETED].groupby("customer_id").size()
    return 100 * ratio((counts >= 2).sum(), len(counts))


def cohort_retention(orders: pd.DataFrame, max_months: int = 12) -> pd.DataFrame:
    """Monthly cohort retention matrix (percent of cohort purchasing in month N).

    Cohort = month of a customer's first *observed* completed order. Orders
    start in January 2024 while some customers signed up in 2023, so early
    cohorts include customers whose true first purchase may be earlier
    (left-censoring); interpret the 2024 cohorts with that in mind.
    """
    completed = prepare_orders(orders[orders["order_status"] == STATUS_COMPLETED])
    first = completed.groupby("customer_id")["order_month"].min().rename("cohort_month")
    completed = completed.join(first, on="customer_id")
    completed["months_since_first"] = (
        (completed["order_month"].dt.year - completed["cohort_month"].dt.year) * 12
        + (completed["order_month"].dt.month - completed["cohort_month"].dt.month)
    )
    active = completed.groupby(["cohort_month", "months_since_first"])["customer_id"].nunique().unstack(fill_value=0)
    cohort_size = active[0]
    retention = 100 * active.div(cohort_size, axis=0)
    # Blank out cells that are in the future relative to the last observed month.
    last_month = completed["order_month"].max()
    for cohort in retention.index:
        observable = (last_month.year - cohort.year) * 12 + (last_month.month - cohort.month)
        retention.loc[cohort, retention.columns > observable] = np.nan
    retention = retention.loc[:, retention.columns <= max_months]
    retention.insert(0, "cohort_size", cohort_size)
    return retention


def average_retention_curve(retention: pd.DataFrame) -> pd.DataFrame:
    """Customer-weighted average retention by months since first purchase."""
    sizes = retention["cohort_size"]
    rows = []
    for month in [c for c in retention.columns if c != "cohort_size"]:
        observed = retention[month].notna()
        weighted = (retention.loc[observed, month] * sizes[observed]).sum() / sizes[observed].sum()
        rows.append({"months_since_first": month, "retention_pct": weighted, "cohorts_observed": int(observed.sum())})
    return pd.DataFrame(rows)


def rfm_table(orders: pd.DataFrame, customers: pd.DataFrame, snapshot_date=SNAPSHOT_DATE) -> pd.DataFrame:
    """Recency / frequency / monetary per customer from completed orders, with 1-5 scores.

    Recency is days since the last completed order of all history; customers
    with no completed order get recency = days since signup and R score 1.
    """
    completed = orders[orders["order_status"] == STATUS_COMPLETED]
    agg = completed.groupby("customer_id").agg(last_order=("order_date", "max"), frequency=("order_id", "size"), monetary_usd=("net_revenue_usd", "sum"))
    rfm = customers.set_index("customer_id")[["signup_date"]].join(agg)
    rfm["has_purchased"] = rfm["frequency"].notna()
    rfm["recency_days"] = (snapshot_date - rfm["last_order"].fillna(rfm["signup_date"])).dt.days
    rfm[["frequency", "monetary_usd"]] = rfm[["frequency", "monetary_usd"]].fillna(0)
    buyers = rfm["has_purchased"]
    # Rank-based quintiles avoid failures from tied values.
    rfm["r_score"] = 1
    rfm.loc[buyers, "r_score"] = pd.qcut(rfm.loc[buyers, "recency_days"].rank(method="first", ascending=False), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["f_score"] = 1
    rfm.loc[buyers, "f_score"] = pd.qcut(rfm.loc[buyers, "frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["m_score"] = 1
    rfm.loc[buyers, "m_score"] = pd.qcut(rfm.loc[buyers, "monetary_usd"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    return rfm.drop(columns=["signup_date", "last_order"]).reset_index()


def two_proportion_test(successes_a: int, total_a: int, successes_b: int, total_b: int) -> dict:
    """Chi-square test of whether two rates differ (e.g. refund rate by channel)."""
    from scipy.stats import chi2_contingency

    table = [[successes_a, total_a - successes_a], [successes_b, total_b - successes_b]]
    chi2, p_value, _, _ = chi2_contingency(table)
    return {
        "rate_a_pct": 100 * ratio(successes_a, total_a),
        "rate_b_pct": 100 * ratio(successes_b, total_b),
        "difference_pp": 100 * (ratio(successes_a, total_a) - ratio(successes_b, total_b)),
        "chi2": float(chi2),
        "p_value": float(p_value),
    }


def unit_economics_by_channel(marketing: pd.DataFrame, orders: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """Spend per new customer next to first-year profit per customer, by channel.

    Both are per-customer dollar figures, so they share one axis. The ratio is
    a rough payback indicator, not a causal ROI: attribution is last-touch
    acquisition_channel as recorded, and costs outside the data (shipping,
    support, overhead) are ignored.
    """
    spend = marketing_efficiency(marketing, customers)[["acquisition_channel", "spend_usd", "new_customers", "spend_per_new_customer_usd"]]
    value = first_year_value_by_channel(orders, customers)[["acquisition_channel", "first_year_profit_per_customer_usd", "first_year_revenue_per_customer_usd"]]
    result = spend.merge(value, on="acquisition_channel")
    result["spend_to_first_year_profit_ratio"] = result["spend_per_new_customer_usd"] / result["first_year_profit_per_customer_usd"]
    return result.sort_values("spend_per_new_customer_usd", ascending=False).reset_index(drop=True)


def marketing_vs_profit_by_year(marketing: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    """Yearly net revenue, product-level profit and marketing spend (2026 = Jan-May)."""
    spend = marketing.groupby(marketing["month"].dt.year)["spend_usd"].sum().rename("marketing_spend_usd")
    sales = orders.groupby(orders["order_date"].dt.year)[["net_revenue_usd", "profit_usd"]].sum()
    result = sales.join(spend, how="inner")
    result["profit_after_marketing_usd"] = result["profit_usd"] - result["marketing_spend_usd"]
    result["marketing_pct_of_revenue"] = 100 * result["marketing_spend_usd"] / result["net_revenue_usd"]
    return result.reset_index(names="year")
