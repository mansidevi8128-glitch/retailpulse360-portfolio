"""KPI definitions on hand-checkable toy data, plus reconciliations on real data."""

import numpy as np
import pandas as pd
import pytest

from retailpulse360 import metrics


def test_executive_summary_definitions(toy_orders):
    customers = pd.DataFrame({"customer_id": ["C1", "C2", "C3"]})
    s = metrics.executive_summary(toy_orders, customers)
    assert s["net_revenue_usd"] == pytest.approx(355.0)
    assert s["gmv_usd"] == pytest.approx(470.0)  # all placed orders
    assert s["profit_usd"] == pytest.approx(97.0)  # refund loss included
    assert s["refund_loss_usd"] == pytest.approx(48.0)
    assert s["aov_usd"] == pytest.approx(355.0 / 3)  # completed orders only
    assert s["refund_rate_pct"] == pytest.approx(25.0)  # 1 refunded / 4 fulfilled
    assert s["cancellation_rate_pct"] == pytest.approx(20.0)  # 1 / 5 placed
    assert s["purchasing_customers"] == 2


def test_monthly_kpis_and_growth(toy_orders):
    monthly = metrics.monthly_kpis(toy_orders).set_index("order_month")
    jan, feb = pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")
    assert monthly.loc[jan, "net_revenue_usd"] == pytest.approx(305.0)
    assert monthly.loc[feb, "net_revenue_usd"] == pytest.approx(50.0)
    assert monthly.loc[feb, "revenue_mom_pct"] == pytest.approx(100 * (50 / 305 - 1))
    assert monthly.loc[jan, "active_customers"] == 2
    assert np.isnan(monthly.loc[jan, "revenue_mom_pct"])


def test_category_performance_has_no_join_fanout(toy_orders, toy_items, toy_products):
    result = metrics.category_performance(toy_orders, toy_items, toy_products).set_index("category")
    completed_gmv = toy_orders.loc[toy_orders["order_status"] == "Completed", "gross_merchandise_value_usd"].sum()
    assert result["revenue_usd"].sum() == pytest.approx(completed_gmv)
    # Office: L1 (60) + L3 (50) completed; L5 refunded loses its 48 cost.
    assert result.loc["Office", "revenue_usd"] == pytest.approx(110.0)
    assert result.loc["Office", "profit_usd"] == pytest.approx(110.0 - 36.0 - 30.0 - 48.0)
    assert result.loc["Office", "refund_loss_usd"] == pytest.approx(48.0)


def test_category_revenue_reconciles_to_net_revenue(tables):
    category = metrics.category_performance(tables["orders"], tables["order_items"], tables["products"])
    orders = tables["orders"]
    shipping = orders.loc[orders["order_status"] == "Completed", "shipping_fee_usd"].sum()
    assert category["revenue_usd"].sum() + shipping == pytest.approx(orders["net_revenue_usd"].sum(), abs=0.05)
    # Category profit + shipping revenue = order-level profit.
    assert category["profit_usd"].sum() + shipping == pytest.approx(orders["profit_usd"].sum(), abs=0.05)


def test_repeat_purchase_rate(toy_orders):
    # C1 has 2 completed orders, C2 has 1 -> 50%.
    assert metrics.repeat_purchase_rate(toy_orders) == pytest.approx(50.0)


def test_purchase_frequency_counts_customers_without_orders(toy_orders):
    customers = pd.DataFrame({"customer_id": ["C1", "C2", "C3"]})
    dist = metrics.purchase_frequency(toy_orders, customers).set_index("completed_orders")["customers"]
    assert dist["0"] == 1 and dist["1"] == 1 and dist["2"] == 1


def test_cohort_retention(toy_orders):
    retention = metrics.cohort_retention(toy_orders)
    jan = retention.loc[pd.Timestamp("2024-01-01")]
    assert jan["cohort_size"] == 2
    assert jan[0] == pytest.approx(100.0)
    assert jan[1] == pytest.approx(50.0)  # only C1 bought again in February


def test_cohort_retention_blanks_unobservable_months(tables):
    retention = metrics.cohort_retention(tables["orders"])
    last_cohort = retention.index.max()
    assert retention.loc[last_cohort, 1:].isna().all()


def test_safe_divide_handles_zero():
    out = metrics.safe_divide(pd.Series([1.0, 2.0]), pd.Series([0.0, 4.0]))
    assert np.isnan(out.iloc[0]) and out.iloc[1] == 0.5
    assert np.isnan(metrics.ratio(1, 0))


def test_marketing_efficiency_ratios(tables):
    result = metrics.marketing_efficiency(tables["marketing_spend"], tables["customers"]).set_index("acquisition_channel")
    raw = tables["marketing_spend"].groupby("channel").sum(numeric_only=True)
    for channel in raw.index:
        assert result.loc[channel, "cost_per_lead_usd"] == pytest.approx(raw.loc[channel, "spend_usd"] / raw.loc[channel, "leads"])
        assert result.loc[channel, "ctr_pct"] == pytest.approx(100 * raw.loc[channel, "clicks"] / raw.loc[channel, "impressions"])
    assert result["spend_usd"].sum() == pytest.approx(tables["marketing_spend"]["spend_usd"].sum())


def test_rfm_scores_in_range(tables):
    rfm = metrics.rfm_table(tables["orders"], tables["customers"])
    assert len(rfm) == len(tables["customers"])
    for column in ["r_score", "f_score", "m_score"]:
        assert rfm[column].between(1, 5).all()
    assert (rfm.loc[~rfm["has_purchased"], ["r_score", "f_score", "m_score"]] == 1).all().all()


def test_two_proportion_test_detects_large_difference():
    result = metrics.two_proportion_test(50, 100, 10, 100)
    assert result["p_value"] < 0.001
    assert result["difference_pp"] == pytest.approx(40.0)
