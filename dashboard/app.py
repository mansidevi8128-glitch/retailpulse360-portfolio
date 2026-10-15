"""RetailPulse 360 executive dashboard (Streamlit + Plotly).

Run from the repository root:
    streamlit run dashboard/app.py

KPIs are recomputed from the raw CSVs for the selected filters, so ratios
such as AOV and refund rate are always recalculated from totals (never
averaged across months). Churn scores and segments come from the files that
`python scripts/run_pipeline.py` writes to reports/.
"""

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from retailpulse360 import metrics  # noqa: E402
from retailpulse360.config import PALETTE, REPORTS_DIR, SYNTHETIC_DISCLAIMER, TABLES_DIR  # noqa: E402
from retailpulse360.data import load_raw_tables  # noqa: E402

st.set_page_config(page_title="RetailPulse 360 Dashboard", layout="wide")

CHART_LAYOUT = dict(template="plotly_white", margin=dict(l=10, r=10, t=50, b=10), hoverlabel=dict(bgcolor="white"), font=dict(size=13))
CATEGORY_COLORS = {}  # filled lazily so each category keeps its colour across filters


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Loading data…")
def load_data():
    tables = load_raw_tables()
    scores_path = TABLES_DIR / "customer_scores.csv"
    scores = pd.read_csv(scores_path) if scores_path.exists() else None
    segments = pd.read_csv(TABLES_DIR / "segment_profiles.csv") if (TABLES_DIR / "segment_profiles.csv").exists() else None
    model_metrics = json.loads((REPORTS_DIR / "model_metrics.json").read_text()) if (REPORTS_DIR / "model_metrics.json").exists() else None
    extra = {}
    for name in ["churn_threshold_table", "churn_capacity_table", "churn_permutation_importance", "churn_cv_results"]:
        path = TABLES_DIR / f"{name}.csv"
        extra[name] = pd.read_csv(path) if path.exists() else None
    return tables, scores, segments, model_metrics, extra


def color_map(values) -> dict:
    for value in sorted(values):
        if value not in CATEGORY_COLORS:
            CATEGORY_COLORS[value] = PALETTE[len(CATEGORY_COLORS) % len(PALETTE)]
    return CATEGORY_COLORS


def usd(value: float, decimals: int = 0) -> str:
    if abs(value) >= 1e6:
        return f"${value / 1e6:,.2f}M"
    if abs(value) >= 1e4:
        return f"${value / 1e3:,.1f}K"
    return f"${value:,.{decimals}f}"


def rounded(df: pd.DataFrame, decimals: int = 2) -> pd.DataFrame:
    """Round numeric columns only (dates are left untouched)."""
    out = df.copy()
    numeric = out.select_dtypes("number").columns
    out[numeric] = out[numeric].round(decimals)
    return out


def style(fig, title: str, height: int = 380):
    fig.update_layout(title=dict(text=title, x=0, xanchor="left"), height=height, **CHART_LAYOUT)
    return fig


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #
tables, scores, segment_profiles, model_metrics, extra = load_data()
customers, orders = tables["customers"], tables["orders"]

st.title("RetailPulse 360 — Executive Dashboard")
st.caption(f"⚠️ {SYNTHETIC_DISCLAIMER}")

months = sorted(orders["order_date"].dt.to_period("M").unique())
with st.sidebar:
    st.header("Filters")
    start, end = st.select_slider("Order months", options=months, value=(months[0], months[-1]), format_func=lambda p: p.strftime("%b %Y"))
    regions = st.multiselect("Customer region", sorted(customers["region"].unique()), placeholder="All regions")
    channels = st.multiselect("Acquisition channel", sorted(customers["acquisition_channel"].unique()), placeholder="All channels")
    sales_channels = st.multiselect("Sales channel", sorted(orders["sales_channel"].unique()), placeholder="All sales channels")
    st.divider()
    st.markdown(
        "**How filters apply**\n\n"
        "- Sales, product, customer and support views follow every filter.\n"
        "- Marketing follows the month and acquisition-channel filters (spend has no region).\n"
        "- Segments and churn scores describe the **2026-05-31 snapshot** and follow region and channel only."
    )

selected_customers = customers
if regions:
    selected_customers = selected_customers[selected_customers["region"].isin(regions)]
if channels:
    selected_customers = selected_customers[selected_customers["acquisition_channel"].isin(channels)]
customer_ids = set(selected_customers["customer_id"])

period = orders["order_date"].dt.to_period("M")
f_orders = orders[(period >= start) & (period <= end) & orders["customer_id"].isin(customer_ids)]
if sales_channels:
    f_orders = f_orders[f_orders["sales_channel"].isin(sales_channels)]
f_items = tables["order_items"][tables["order_items"]["order_id"].isin(f_orders["order_id"])]
ticket_period = tables["support_tickets"]["opened_date"].dt.to_period("M")
f_tickets = tables["support_tickets"][(ticket_period >= start) & (ticket_period <= end) & tables["support_tickets"]["customer_id"].isin(customer_ids)]
mkt_period = tables["marketing_spend"]["month"].dt.to_period("M")
f_marketing = tables["marketing_spend"][(mkt_period >= start) & (mkt_period <= end)]
if channels:
    f_marketing = f_marketing[f_marketing["channel"].isin(channels)]

if f_orders.empty:
    st.warning("No orders match the selected filters.")
    st.stop()

summary = metrics.executive_summary(f_orders, selected_customers)
monthly = metrics.monthly_kpis(f_orders)

tabs = st.tabs(["Executive summary", "Products & regions", "Marketing", "Retention", "Refunds & support", "Segments", "Churn risk", "Definitions"])

# --------------------------------------------------------------------------- #
# Executive summary
# --------------------------------------------------------------------------- #
with tabs[0]:
    st.subheader(f"{start.strftime('%b %Y')} – {end.strftime('%b %Y')}")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Net revenue", usd(summary["net_revenue_usd"]), help="Completed orders: merchandise after discounts + shipping fee, excluding tax.")
    c2.metric("Product-level profit", usd(summary["profit_usd"]), help="Net revenue − merchandise cost, including losses on refunded orders. Excludes shipping, support, overhead and marketing costs.")
    c3.metric("Profit margin", f"{summary['profit_margin_pct']:.1f}%", help="Profit ÷ net revenue.")
    c4.metric("Completed orders", f"{summary['completed_orders']:,}")
    c5.metric("AOV", usd(summary["aov_usd"], 2), help="Net revenue ÷ completed orders.")
    c6.metric("Refund rate", f"{summary['refund_rate_pct']:.1f}%", help="Refunded ÷ (completed + refunded) orders.")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("GMV", usd(summary["gmv_usd"]), help="Post-discount merchandise value of all placed orders (any status). Measures demand, not revenue.")
    c2.metric("Purchasing customers", f"{summary['purchasing_customers']:,}")
    c3.metric("Refund loss", usd(summary["refund_loss_usd"]), help="Merchandise cost written off on refunded orders.")
    c4.metric("Cancellation rate", f"{summary['cancellation_rate_pct']:.1f}%")
    c5.metric("Marketing spend", usd(f_marketing["spend_usd"].sum()), help="Recorded channel spend for the selected months/channels. Not deducted from profit.")
    c6.metric("Orders placed", f"{summary['orders_placed']:,}")

    trend = monthly.melt(id_vars="order_month", value_vars=["net_revenue_usd", "profit_usd"], var_name="measure", value_name="usd")
    trend["measure"] = trend["measure"].map({"net_revenue_usd": "Net revenue", "profit_usd": "Profit"})
    fig = px.line(trend, x="order_month", y="usd", color="measure", color_discrete_sequence=PALETTE, labels={"order_month": "", "usd": "USD", "measure": ""})
    fig.update_traces(hovertemplate="%{x|%b %Y}: $%{y:,.0f}")
    fig.update_yaxes(tickprefix="$", rangemode="tozero")
    st.plotly_chart(style(fig, "Monthly net revenue and profit"), width="stretch")

    left, right = st.columns(2)
    fig = px.line(monthly, x="order_month", y="active_customers", color_discrete_sequence=PALETTE, labels={"order_month": "", "active_customers": "Customers"})
    fig.update_traces(hovertemplate="%{x|%b %Y}: %{y:,} purchasing customers")
    fig.update_yaxes(rangemode="tozero")
    left.plotly_chart(style(fig, "Monthly purchasing customers", 320), width="stretch")
    fig = px.line(monthly, x="order_month", y="aov_usd", color_discrete_sequence=PALETTE, labels={"order_month": "", "aov_usd": "AOV"})
    fig.update_traces(hovertemplate="%{x|%b %Y}: $%{y:,.2f}")
    fig.update_yaxes(tickprefix="$", rangemode="tozero")
    right.plotly_chart(style(fig, "Average order value", 320), width="stretch")

    with st.expander("Monthly KPI table"):
        st.dataframe(rounded(monthly.drop(columns=["revenue_yoy_pct"]), 2), width="stretch", hide_index=True)

# --------------------------------------------------------------------------- #
# Products & regions
# --------------------------------------------------------------------------- #
with tabs[1]:
    category = metrics.category_performance(f_orders, f_items, tables["products"])
    left, right = st.columns(2)
    fig = px.bar(category.sort_values("profit_usd"), x="profit_usd", y="category", orientation="h", color_discrete_sequence=PALETTE, labels={"profit_usd": "Profit (USD)", "category": ""}, text_auto="$.3s")
    fig.update_traces(hovertemplate="%{y}: $%{x:,.0f} profit")
    left.plotly_chart(style(fig, "Profit by category"), width="stretch")
    fig = px.bar(category.sort_values("gross_margin_pct"), x="gross_margin_pct", y="category", orientation="h", color_discrete_sequence=PALETTE, labels={"gross_margin_pct": "Gross margin %", "category": ""}, text_auto=".1f")
    fig.update_traces(hovertemplate="%{y}: %{x:.1f}% margin")
    right.plotly_chart(style(fig, "Gross margin by category (%)"), width="stretch")
    st.caption("Category revenue excludes shipping fees. Profit = completed-line revenue − cost of completed and refunded lines.")
    st.dataframe(rounded(category, 2), width="stretch", hide_index=True)

    region = metrics.customer_dimension_performance(f_orders, selected_customers, "region")
    acq = metrics.customer_dimension_performance(f_orders, selected_customers, "acquisition_channel")
    left, right = st.columns(2)
    fig = px.bar(region.sort_values("revenue_per_customer_usd"), x="revenue_per_customer_usd", y="region", orientation="h", color_discrete_sequence=PALETTE, labels={"revenue_per_customer_usd": "Net revenue per customer", "region": ""}, text_auto="$,.0f")
    fig.update_traces(hovertemplate="%{y}: $%{x:,.0f} per customer")
    left.plotly_chart(style(fig, "Revenue per customer by region", 320), width="stretch")
    fig = px.bar(acq.sort_values("revenue_per_customer_usd"), x="revenue_per_customer_usd", y="acquisition_channel", orientation="h", color_discrete_sequence=PALETTE, labels={"revenue_per_customer_usd": "Net revenue per customer", "acquisition_channel": ""}, text_auto="$,.0f")
    fig.update_traces(hovertemplate="%{y}: $%{x:,.0f} per customer")
    right.plotly_chart(style(fig, "Revenue per customer by acquisition channel", 320), width="stretch")
    sales = metrics.order_dimension_performance(f_orders, "sales_channel")
    st.markdown("**Sales channels**")
    st.dataframe(rounded(sales[["sales_channel", "completed_orders", "net_revenue_usd", "profit_usd", "aov_usd", "profit_margin_pct", "refund_rate_pct", "revenue_share_pct"]], 2), width="stretch", hide_index=True)

# --------------------------------------------------------------------------- #
# Marketing
# --------------------------------------------------------------------------- #
with tabs[2]:
    if f_marketing.empty:
        st.info("No marketing rows for the selected filters.")
    else:
        efficiency = metrics.marketing_efficiency(f_marketing, customers)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Spend", usd(efficiency["spend_usd"].sum()))
        c2.metric("Leads", f"{efficiency['leads'].sum():,}")
        c3.metric("Cost per lead", usd(efficiency["spend_usd"].sum() / efficiency["leads"].sum(), 2))
        c4.metric("CTR", f"{100 * efficiency['clicks'].sum() / efficiency['impressions'].sum():.2f}%", help="Clicks ÷ impressions.")
        left, right = st.columns(2)
        fig = px.bar(efficiency.sort_values("cost_per_lead_usd"), x="cost_per_lead_usd", y="acquisition_channel", orientation="h", color_discrete_sequence=PALETTE, labels={"cost_per_lead_usd": "Cost per lead (USD)", "acquisition_channel": ""}, text_auto="$.2f")
        fig.update_traces(hovertemplate="%{y}: $%{x:.2f} per lead")
        left.plotly_chart(style(fig, "Cost per lead by channel"), width="stretch")
        fig = px.bar(efficiency.sort_values("spend_per_new_customer_usd"), x="spend_per_new_customer_usd", y="acquisition_channel", orientation="h", color_discrete_sequence=PALETTE, labels={"spend_per_new_customer_usd": "Spend per new customer (USD)", "acquisition_channel": ""}, text_auto="$,.0f")
        fig.update_traces(hovertemplate="%{y}: $%{x:,.0f} per new customer")
        right.plotly_chart(style(fig, "Spend per new customer (sign-ups in the selected months)"), width="stretch")
        st.caption("Spend per new customer = channel spend ÷ customers whose recorded acquisition_channel is that channel and who signed up in the selected months. It is an attribution-based ratio, not a measure of incremental impact.")
        monthly_mkt = metrics.monthly_marketing(f_marketing)
        fig = px.line(monthly_mkt, x="month", y="spend_usd", color_discrete_sequence=PALETTE, labels={"month": "", "spend_usd": "Spend"})
        fig.update_traces(hovertemplate="%{x|%b %Y}: $%{y:,.0f}")
        fig.update_yaxes(tickprefix="$", rangemode="tozero")
        st.plotly_chart(style(fig, "Monthly marketing spend", 320), width="stretch")
        st.dataframe(rounded(efficiency, 2), width="stretch", hide_index=True)

# --------------------------------------------------------------------------- #
# Retention
# --------------------------------------------------------------------------- #
with tabs[3]:
    st.caption("Repeat purchase and retention use completed orders in the selected period. Cohort = month of the first observed purchase in that period.")
    c1, c2 = st.columns(2)
    c1.metric("Repeat-purchase rate", f"{metrics.repeat_purchase_rate(f_orders):.1f}%", help="Purchasing customers with 2+ completed orders.")
    frequency = metrics.purchase_frequency(f_orders, selected_customers)
    c2.metric("Customers with no purchase in period", f"{int(frequency.loc[frequency['completed_orders'] == '0', 'customers'].sum()):,}")
    fig = px.bar(frequency, x="completed_orders", y="customers", color_discrete_sequence=PALETTE, labels={"completed_orders": "Completed orders per customer", "customers": "Customers"}, text_auto=",")
    fig.update_traces(hovertemplate="%{x} orders: %{y:,} customers")
    st.plotly_chart(style(fig, "Purchase-frequency distribution", 320), width="stretch")
    retention = metrics.cohort_retention(f_orders)
    matrix = retention.drop(columns=["cohort_size", 0])
    fig = go.Figure(go.Heatmap(z=matrix.to_numpy(), x=[str(c) for c in matrix.columns], y=[f"{d:%Y-%m} (n={n})" for d, n in zip(matrix.index, retention["cohort_size"])], colorscale="Blues", hovertemplate="Cohort %{y}<br>Month %{x}: %{z:.1f}%<extra></extra>", colorbar=dict(title="%")))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title="Months since first purchase")
    st.plotly_chart(style(fig, "Cohort retention (% of cohort purchasing N months later)", 650), width="stretch")

# --------------------------------------------------------------------------- #
# Refunds & support
# --------------------------------------------------------------------------- #
with tabs[4]:
    disc = metrics.discount_band_performance(f_orders)
    left, right = st.columns(2)
    fig = px.bar(disc, x="discount_band", y="profit_margin_pct", color_discrete_sequence=PALETTE, labels={"discount_band": "Order discount", "profit_margin_pct": "Profit margin %"}, text_auto=".1f")
    fig.update_traces(hovertemplate="%{x}: %{y:.1f}% margin")
    left.plotly_chart(style(fig, "Profit margin by discount band", 340), width="stretch")
    fig = px.bar(disc, x="discount_band", y="refund_rate_pct", color_discrete_sequence=PALETTE, labels={"discount_band": "Order discount", "refund_rate_pct": "Refund rate %"}, text_auto=".1f")
    fig.update_traces(hovertemplate="%{x}: %{y:.1f}% refunded")
    right.plotly_chart(style(fig, "Refund rate by discount band", 340), width="stretch")
    if f_tickets.empty:
        st.info("No support tickets for the selected filters.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Support tickets", f"{len(f_tickets):,}")
        c2.metric("Average CSAT (1–5)", f"{f_tickets['csat_score'].mean():.2f}")
        c3.metric("Median resolution", f"{f_tickets['resolution_hours'].median():.1f} h")
        load = metrics.monthly_support_load(f_tickets, f_orders)
        left, right = st.columns(2)
        fig = px.line(load, x="month", y="tickets_per_100_orders", color_discrete_sequence=PALETTE, labels={"month": "", "tickets_per_100_orders": "Tickets per 100 orders"})
        fig.update_traces(hovertemplate="%{x|%b %Y}: %{y:.1f} tickets per 100 fulfilled orders")
        fig.update_yaxes(rangemode="tozero")
        left.plotly_chart(style(fig, "Tickets per 100 fulfilled orders", 340), width="stretch")
        res = metrics.resolution_time_vs_csat(f_tickets)
        fig = px.bar(res, x="resolution_band", y="satisfied_pct", color_discrete_sequence=PALETTE, labels={"resolution_band": "Resolution time", "satisfied_pct": "Satisfied % (CSAT ≥ 4)"}, text_auto=".1f")
        fig.update_traces(hovertemplate="%{x}: %{y:.1f}% satisfied")
        right.plotly_chart(style(fig, "Satisfaction by resolution time", 340), width="stretch")
        st.dataframe(rounded(metrics.support_summary(f_tickets), 2), width="stretch", hide_index=True)

# --------------------------------------------------------------------------- #
# Segments
# --------------------------------------------------------------------------- #
with tabs[5]:
    if scores is None:
        st.info("Run `python scripts/run_pipeline.py` to generate segments and churn scores.")
    else:
        st.caption("K-Means segments built on RFM, discount, refund, engagement and support features at the 2026-05-31 snapshot. The churn label was not used to build them.")
        seg = scores[scores["customer_id"].isin(customer_ids)]
        summary_seg = seg.groupby("segment").agg(customers=("customer_id", "size"), avg_profit_12m=("profit_12m", "mean"), total_profit_12m=("profit_12m", "sum"), observed_churn_pct=("churned_next_90d", "mean"), avg_churn_score=("churn_probability", "mean")).reset_index()
        summary_seg["observed_churn_pct"] *= 100
        summary_seg["share_pct"] = 100 * summary_seg["customers"] / summary_seg["customers"].sum()
        colors = color_map(scores["segment"].unique())
        left, right = st.columns(2)
        fig = px.bar(summary_seg.sort_values("customers"), x="customers", y="segment", orientation="h", color="segment", color_discrete_map=colors, labels={"customers": "Customers", "segment": ""}, text_auto=",")
        fig.update_traces(hovertemplate="%{y}: %{x:,} customers")
        fig.update_layout(showlegend=False)
        left.plotly_chart(style(fig, "Customers per segment", 320), width="stretch")
        fig = px.bar(summary_seg.sort_values("total_profit_12m"), x="total_profit_12m", y="segment", orientation="h", color="segment", color_discrete_map=colors, labels={"total_profit_12m": "12-month profit (USD)", "segment": ""}, text_auto="$.3s")
        fig.update_traces(hovertemplate="%{y}: $%{x:,.0f}")
        fig.update_layout(showlegend=False)
        right.plotly_chart(style(fig, "12-month profit per segment", 320), width="stretch")
        st.dataframe(rounded(summary_seg, 2), width="stretch", hide_index=True)
        if segment_profiles is not None:
            with st.expander("Full segment profiles (all customers)"):
                st.dataframe(rounded(segment_profiles, 3), width="stretch", hide_index=True)

# --------------------------------------------------------------------------- #
# Churn risk
# --------------------------------------------------------------------------- #
with tabs[6]:
    if scores is None or model_metrics is None:
        st.info("Run `python scripts/run_pipeline.py` to generate churn scores.")
    else:
        churn = model_metrics["churn"]
        test = churn["test_metrics_at_threshold"]
        st.warning("Model-derived results on a **synthetic** churn label. They show the method, not real-world predictive accuracy.")
        st.caption(f"Selected model: **{churn['chosen_model']}**, evaluated on a 25% stratified hold-out test set. Threshold {churn['threshold']:.2f} was chosen to maximise F1 on out-of-fold training predictions.")
        c2, c3, c4, c5 = st.columns(4)
        c2.metric("Test ROC-AUC", f"{test['roc_auc']:.3f}", help="Probability that a random churner is ranked above a random non-churner.")
        c3.metric("Test PR-AUC", f"{test['pr_auc']:.3f}", help=f"Average precision. A random model scores the base rate, {churn['base_rate_test']:.1%}.")
        c4.metric(f"Precision @ {churn['threshold']:.2f}", f"{test['precision']:.2f}")
        c5.metric(f"Recall @ {churn['threshold']:.2f}", f"{test['recall']:.2f}")
        seg = scores[scores["customer_id"].isin(customer_ids)]
        left, right = st.columns(2)
        bands = seg.groupby("risk_band", observed=True).agg(customers=("customer_id", "size"), observed_churn=("churned_next_90d", "mean")).reindex(["Low", "Medium", "High"]).reset_index()
        bands["observed_churn"] *= 100
        fig = px.bar(bands, x="risk_band", y="customers", color_discrete_sequence=PALETTE, labels={"risk_band": "Risk band (score <0.3 / 0.3–0.6 / ≥0.6)", "customers": "Customers"}, text_auto=",", hover_data={"observed_churn": ":.1f"})
        left.plotly_chart(style(fig, "Customers by out-of-fold risk band", 340), width="stretch")
        if extra["churn_capacity_table"] is not None:
            cap = extra["churn_capacity_table"]
            fig = px.line(cap, x="contact_share_pct", y="recall", markers=True, color_discrete_sequence=PALETTE, labels={"contact_share_pct": "Share of customers contacted (riskiest first, %)", "recall": "Share of churners reached"})
            fig.update_traces(hovertemplate="Contact top %{x:.0f}% → reach %{y:.0%} of churners")
            fig.update_yaxes(tickformat=".0%", range=[0, 1])
            right.plotly_chart(style(fig, "Churners reached vs outreach capacity (test set)", 340), width="stretch")
        if extra["churn_permutation_importance"] is not None:
            imp = extra["churn_permutation_importance"].head(10).sort_values("importance_mean")
            fig = px.bar(imp, x="importance_mean", y="feature", orientation="h", color_discrete_sequence=PALETTE, labels={"importance_mean": "Drop in ROC-AUC when shuffled", "feature": ""}, error_x="importance_std")
            st.plotly_chart(style(fig, "Most important features (permutation importance, test set)", 400), width="stretch")
        st.markdown("**Highest-risk customers** (out-of-fold scores, so every customer is scored by a model that did not see their label)")
        top = seg.sort_values("churn_probability", ascending=False).head(25)
        st.dataframe(top[["customer_id", "segment", "loyalty_tier", "region", "days_since_last_purchase", "frequency_12m", "monetary_value_12m", "churn_probability"]], width="stretch", hide_index=True)

# --------------------------------------------------------------------------- #
# Definitions
# --------------------------------------------------------------------------- #
with tabs[7]:
    st.markdown(
        """
| Metric | Definition |
|---|---|
| **Net revenue** | `net_revenue_usd` on Completed orders = merchandise after discounts + shipping fee. Tax excluded. Refunded and cancelled orders = 0. |
| **GMV** | Post-discount merchandise value of every placed order (any status), excluding shipping and tax. |
| **Profit** | Net revenue − merchandise cost. Refunded orders lose their merchandise cost. Excludes shipping, support, overhead and marketing costs. |
| **AOV** | Net revenue ÷ completed orders. |
| **Refund rate** | Refunded ÷ (completed + refunded) orders. |
| **Cancellation rate** | Cancelled ÷ all placed orders. |
| **Purchasing customers** | Distinct customers with ≥ 1 completed order in the period. |
| **Repeat-purchase rate** | Purchasing customers with ≥ 2 completed orders. |
| **CTR / CPL** | Clicks ÷ impressions / spend ÷ leads. |
| **Spend per new customer** | Channel spend ÷ new sign-ups attributed to that acquisition channel in the same months. |
| **Churn score** | Out-of-fold probability from the selected model that the customer churns within 90 days of 2026-05-31 (synthetic label). |

Full definitions: `docs/metric_definitions.md`.
"""
    )
