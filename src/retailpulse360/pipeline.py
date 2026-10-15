"""End-to-end analysis steps shared by the report script, notebooks and tests."""

import pandas as pd
from sklearn.base import clone
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from . import features as feat
from . import metrics, modeling, quality, segmentation
from .config import RANDOM_STATE
from .data import load_raw_tables, load_snapshot

SIMPLER_MODEL_TOLERANCE = 0.01  # prefer Logistic Regression if within this CV PR-AUC


def load_model_frame(tables: dict | None = None) -> pd.DataFrame:
    """Provided snapshot + corrected recency/purchase flags."""
    tables = tables or load_raw_tables()
    return feat.add_corrected_features(load_snapshot(), tables["orders"])


def run_quality_audit(tables: dict, snapshot: pd.DataFrame) -> dict:
    rebuilt = feat.build_customer_features(tables)
    profiles = pd.concat([quality.profile_table(name, df) for name, df in tables.items()], ignore_index=True)
    return {
        "overview": quality.table_overview(tables),
        "profiles": profiles,
        "primary_keys": quality.check_primary_keys(tables),
        "foreign_keys": quality.check_foreign_keys(tables),
        "business_rules": quality.business_rule_checks(tables),
        "reconciliation": quality.reconcile_order_financials(tables["orders"], tables["order_items"]),
        "outliers": quality.outlier_summary(tables),
        "snapshot_reproduction": quality.snapshot_reproduction_check(snapshot, rebuilt, feat.SNAPSHOT_NUMERIC_FEATURES),
        "snapshot_rows": len(snapshot),
        "snapshot_missing_cells": int(snapshot.isna().sum().sum()),
        "snapshot_duplicate_ids": int(snapshot["customer_id"].duplicated().sum()),
    }


def select_model(cv_results: pd.DataFrame) -> str:
    best = cv_results.loc[cv_results["cv_pr_auc_mean"].idxmax()]
    baseline = cv_results.set_index("model").loc["Logistic Regression"]
    if best["cv_pr_auc_mean"] - baseline["cv_pr_auc_mean"] <= SIMPLER_MODEL_TOLERANCE:
        return "Logistic Regression"
    return str(best["model"])


def run_churn_analysis(frame: pd.DataFrame) -> dict:
    X, y = modeling.feature_matrix(frame)
    X_train, X_test, y_train, y_test = modeling.split_data(X, y)
    models = modeling.build_models()
    cv_results = modeling.cross_validate_models(models, X_train, y_train)

    test_rows, test_probabilities, fitted = [], {}, {}
    for name, model in models.items():
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]
        fitted[name] = model
        test_probabilities[name] = proba
        test_rows.append({"model": name, **modeling.classification_metrics(y_test, proba)})
    test_results = pd.DataFrame(test_rows)

    chosen = select_model(cv_results)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    # Threshold chosen on out-of-fold *training* predictions, then applied to test.
    train_oof = cross_val_predict(clone(models[chosen]), X_train, y_train, cv=cv, method="predict_proba")[:, 1]
    threshold = modeling.best_f1_threshold(y_train, train_oof)
    chosen_proba = test_probabilities[chosen]
    chosen_metrics = modeling.classification_metrics(y_test, chosen_proba, threshold)

    # Out-of-fold scores for every customer, for dashboard risk summaries.
    all_oof = cross_val_predict(clone(models[chosen]), X, y, cv=cv, method="predict_proba")[:, 1]

    importance = modeling.permutation_importance_table(fitted[chosen], X_test, y_test)
    coefficients = modeling.logistic_coefficients(fitted["Logistic Regression"])
    return {
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "models": fitted,
        "cv_results": cv_results,
        "test_results": test_results,
        "test_probabilities": test_probabilities,
        "chosen_model": chosen,
        "threshold": threshold,
        "chosen_metrics": chosen_metrics,
        "default_threshold_metrics": modeling.classification_metrics(y_test, chosen_proba, 0.5),
        "threshold_table": modeling.threshold_table(y_test, chosen_proba),
        "capacity_table": modeling.capacity_table(y_test, chosen_proba),
        "permutation_importance": importance,
        "coefficients": coefficients,
        "base_rate_train": float(y_train.mean()),
        "base_rate_test": float(y_test.mean()),
        "oof_probability": pd.Series(all_oof, index=frame.index, name="churn_probability"),
    }


def run_segmentation(frame: pd.DataFrame) -> dict:
    matrix = segmentation.segment_matrix(frame)
    k_evaluation = segmentation.evaluate_k(matrix)
    k = segmentation.choose_k(k_evaluation)
    model = segmentation.fit_kmeans(matrix, k)
    profile = segmentation.profile_segments(frame, model.labels_)
    names = segmentation.name_segments(profile)
    profile.insert(0, "segment", profile.index.map(names))
    return {
        "matrix": matrix,
        "k_evaluation": k_evaluation,
        "k": k,
        "labels": model.labels_,
        "segment_names": names,
        "profile": profile,
        "skew": segmentation.skew_table(frame),
        "stability": segmentation.stability(matrix, k),
    }


def business_tables(tables: dict) -> dict:
    orders, customers = tables["orders"], tables["customers"]
    return {
        "executive_summary": metrics.executive_summary(orders, customers),
        "monthly_kpis": metrics.monthly_kpis(orders),
        "yearly_kpis_jan_may": metrics.yearly_kpis(orders),
        "category_performance": metrics.category_performance(orders, tables["order_items"], tables["products"]),
        "region_performance": metrics.customer_dimension_performance(orders, customers, "region"),
        "acquisition_channel_performance": metrics.customer_dimension_performance(orders, customers, "acquisition_channel"),
        "loyalty_tier_performance": metrics.customer_dimension_performance(orders, customers, "loyalty_tier"),
        "sales_channel_performance": metrics.order_dimension_performance(orders, "sales_channel"),
        "payment_method_performance": metrics.order_dimension_performance(orders, "payment_method"),
        "shipping_type_performance": metrics.order_dimension_performance(orders, "shipping_type"),
        "discount_band_performance": metrics.discount_band_performance(orders),
        "first_year_value_by_channel": metrics.first_year_value_by_channel(orders, customers),
        "marketing_efficiency": metrics.marketing_efficiency(tables["marketing_spend"], customers),
        "marketing_vs_profit_by_year": metrics.marketing_vs_profit_by_year(tables["marketing_spend"], orders),
        "unit_economics_by_channel": metrics.unit_economics_by_channel(tables["marketing_spend"], orders, customers),
        "monthly_marketing": metrics.monthly_marketing(tables["marketing_spend"]),
        "funnel_overall": metrics.session_funnel(tables["web_sessions"]),
        "funnel_by_device": metrics.session_funnel(tables["web_sessions"], "device"),
        "funnel_by_traffic_source": metrics.session_funnel(tables["web_sessions"], "traffic_source"),
        "support_by_issue": metrics.support_summary(tables["support_tickets"], "issue_type"),
        "support_by_priority": metrics.support_summary(tables["support_tickets"], "priority"),
        "resolution_vs_csat": metrics.resolution_time_vs_csat(tables["support_tickets"]),
        "monthly_support": metrics.monthly_support_load(tables["support_tickets"], orders),
        "purchase_frequency": metrics.purchase_frequency(orders, customers),
        "repeat_purchase_rate_pct": metrics.repeat_purchase_rate(orders),
        "cohort_retention": metrics.cohort_retention(orders),
        "rfm": metrics.rfm_table(orders, customers),
    }


def customer_scores(frame: pd.DataFrame, churn: dict, segments: dict) -> pd.DataFrame:
    """One row per customer: attributes, segment, out-of-fold churn probability."""
    out = frame[["customer_id", "region", "acquisition_channel", "preferred_device", "loyalty_tier", "days_since_last_purchase", "frequency_12m", "monetary_value_12m", "profit_12m", feat.TARGET]].copy()
    out["segment"] = pd.Series(segments["labels"], index=frame.index).map(segments["segment_names"])
    out["churn_probability"] = churn["oof_probability"].round(4)
    out["risk_band"] = modeling.risk_band(out["churn_probability"].to_numpy()).astype(str).to_numpy()
    out["flagged_at_threshold"] = (out["churn_probability"] >= churn["threshold"]).astype(int)
    return out


def statistical_checks(tables: dict, frame: pd.DataFrame) -> dict:
    """Significance tests behind comparisons quoted in the reports."""
    o = metrics.prepare_orders(tables["orders"])
    fulfilled = o[o["is_fulfilled"] == 1]

    def refunds(mask):
        subset = fulfilled[mask]
        return int(subset["is_refunded"].sum()), len(subset)

    marketplace = refunds(fulfilled["sales_channel"] == "Marketplace")
    website = refunds(fulfilled["sales_channel"] == "Website")
    discounted = refunds(fulfilled["discount_pct"] > 0)
    full_price = refunds(fulfilled["discount_pct"] == 0)
    bronze = frame[frame["loyalty_tier"] == "Bronze"][feat.TARGET]
    platinum = frame[frame["loyalty_tier"] == "Platinum"][feat.TARGET]
    return {
        "refund_rate_marketplace_vs_website": metrics.two_proportion_test(*marketplace, *website),
        "refund_rate_discounted_vs_full_price": metrics.two_proportion_test(*discounted, *full_price),
        "churn_rate_bronze_vs_platinum": metrics.two_proportion_test(int(bronze.sum()), len(bronze), int(platinum.sum()), len(platinum)),
    }


def headline_numbers(business: dict) -> dict:
    """Small derived facts used in written reports (all computed, none typed by hand)."""
    monthly = business["monthly_kpis"]
    yearly = business["yearly_kpis_jan_may"].set_index("year")
    category = business["category_performance"]
    channel_value = business["first_year_value_by_channel"]
    marketing = business["marketing_efficiency"]
    support = business["monthly_support"]
    summary = business["executive_summary"]
    total_marketing = float(marketing["spend_usd"].sum())
    return {
        "marketing_spend_usd": total_marketing,
        "profit_after_marketing_usd": summary["profit_usd"] - total_marketing,
        "tickets_per_100_orders_first": float(support["tickets_per_100_orders"].iloc[0]),
        "tickets_per_100_orders_last": float(support["tickets_per_100_orders"].iloc[-1]),
        "csat_first_12m": float(support["avg_csat"].iloc[:12].mean()),
        "csat_last_12m": float(support["avg_csat"].iloc[-12:].mean()),
        "first_month": monthly["order_month"].min().strftime("%b %Y"),
        "last_month": monthly["order_month"].max().strftime("%b %Y"),
        "first_month_revenue": float(monthly["net_revenue_usd"].iloc[0]),
        "last_month_revenue": float(monthly["net_revenue_usd"].iloc[-1]),
        "ytd_revenue_growth_2026_vs_2025_pct": float(100 * (yearly.loc[2026, "net_revenue_usd"] / yearly.loc[2025, "net_revenue_usd"] - 1)),
        "ytd_profit_growth_2026_vs_2025_pct": float(100 * (yearly.loc[2026, "profit_usd"] / yearly.loc[2025, "profit_usd"] - 1)),
        "ytd_aov_2025": float(yearly.loc[2025, "aov_usd"]),
        "ytd_aov_2026": float(yearly.loc[2026, "aov_usd"]),
        "ytd_margin_2025": float(yearly.loc[2025, "profit_margin_pct"]),
        "ytd_margin_2026": float(yearly.loc[2026, "profit_margin_pct"]),
        "ytd_active_2025": int(yearly.loc[2025, "active_customers"]),
        "ytd_active_2026": int(yearly.loc[2026, "active_customers"]),
        "top_revenue_category": category.iloc[0]["category"],
        "top_profit_category": category.sort_values("profit_usd", ascending=False).iloc[0]["category"],
        "highest_margin_category": category.sort_values("gross_margin_pct", ascending=False).iloc[0]["category"],
        "lowest_margin_category": category.sort_values("gross_margin_pct").iloc[0]["category"],
        "best_first_year_channel": channel_value.iloc[0]["acquisition_channel"],
        "worst_first_year_channel": channel_value.iloc[-1]["acquisition_channel"],
        "lowest_cpl_channel": marketing.sort_values("cost_per_lead_usd").iloc[0]["acquisition_channel"],
        "highest_cpl_channel": marketing.sort_values("cost_per_lead_usd").iloc[-1]["acquisition_channel"],
        "negative_mom_months": int((monthly["revenue_mom_pct"] < 0).sum()),
    }


def correlation_with_target(frame: pd.DataFrame) -> pd.Series:
    return frame[feat.MODEL_NUMERIC_FEATURES].corrwith(frame[feat.TARGET]).sort_values()

