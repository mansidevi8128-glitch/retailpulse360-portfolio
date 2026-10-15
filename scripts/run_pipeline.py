"""Regenerate every analytical output from the raw data.

Usage (from the repository root):
    python scripts/run_pipeline.py

Writes:
    reports/data_quality_report.md
    reports/business_recommendations.md
    reports/tables/*.csv           KPI, model and segment tables
    reports/model_metrics.json     churn-model metrics
    reports/figures/*.png          charts used in the README
    README.md                      the KEY-FINDINGS block only
Raw CSV files are only read, never written.
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from retailpulse360 import pipeline, plotting, reporting  # noqa: E402
from retailpulse360.config import PALETTE, PROJECT_ROOT, REPORTS_DIR, TABLES_DIR  # noqa: E402
from retailpulse360.data import load_raw_tables, load_snapshot  # noqa: E402
from retailpulse360.metrics import average_retention_curve  # noqa: E402


def save_table(df, name: str, index: bool = False) -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    numeric = out.select_dtypes("number").columns
    out[numeric] = out[numeric].round(4)
    out.to_csv(TABLES_DIR / f"{name}.csv", index=index)


def business_figures(business: dict) -> None:
    monthly = business["monthly_kpis"]

    fig, ax = plt.subplots(figsize=(9, 3.8))
    plotting.line_chart(monthly, "order_month", "net_revenue_usd", "Monthly net revenue and product-level profit", ax=ax, label="Net revenue")
    ax.plot(monthly["order_month"], monthly["profit_usd"], color=PALETTE[1], label="Profit")
    plotting.money(ax)
    ax.legend(loc="upper left")
    plotting.save(fig, "monthly_revenue_profit")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 3.6))
    plotting.line_chart(monthly, "order_month", "active_customers", "Monthly purchasing customers", ylabel="Customers", ax=ax)
    plotting.save(fig, "monthly_active_customers")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 3.6))
    plotting.line_chart(monthly, "order_month", "aov_usd", "Average order value (completed orders)", ax=ax)
    ax.set_ylim(0, monthly["aov_usd"].max() * 1.15)
    plotting.money(ax, decimals=0)
    plotting.save(fig, "monthly_aov")
    plt.close(fig)

    category = business["category_performance"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 3.8))
    plotting.barh_chart(category, "category", "profit_usd", "Profit by category", fmt="${:,.0f}", ax=ax1)
    plotting.money(ax1, axis="x")
    plotting.barh_chart(category, "category", "gross_margin_pct", "Gross margin by category", fmt="{:.1f}%", ax=ax2)
    plotting.percent(ax2, axis="x")
    fig.tight_layout()
    plotting.save(fig, "category_profit_margin")
    plt.close(fig)

    ue = business["unit_economics_by_channel"]
    fig, ax = plt.subplots(figsize=(9, 4))
    y = range(len(ue))
    ax.barh([i + 0.2 for i in y], ue["spend_per_new_customer_usd"], height=0.38, color=PALETTE[0], label="Marketing spend per new customer")
    ax.barh([i - 0.2 for i in y], ue["first_year_profit_per_customer_usd"], height=0.38, color=PALETTE[1], label="First-year profit per customer")
    ax.set_yticks(list(y), ue["acquisition_channel"])
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    plotting.money(ax, axis="x")
    ax.set_title("Acquisition cost vs first-year profit per customer")
    ax.legend(loc="lower right")
    plotting.save(fig, "channel_unit_economics")
    plt.close(fig)

    disc = business["discount_band_performance"]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    plotting.barh_chart(disc, "discount_band", "profit_margin_pct", "Profit margin by order discount", fmt="{:.1f}%", ax=ax, sort=False)
    plotting.percent(ax, axis="x")
    plotting.save(fig, "discount_margin")
    plt.close(fig)

    support = business["monthly_support"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 3.8))
    plotting.line_chart(support, "month", "tickets_per_100_orders", "Support tickets per 100 fulfilled orders", ax=ax1)
    plotting.barh_chart(business["resolution_vs_csat"], "resolution_band", "satisfied_pct", "Satisfied customers (CSAT ≥ 4) by resolution time", fmt="{:.1f}%", ax=ax2, sort=False)
    plotting.percent(ax2, axis="x")
    fig.tight_layout()
    plotting.save(fig, "support_load_csat")
    plt.close(fig)

    retention = business["cohort_retention"]
    matrix = retention.drop(columns=["cohort_size", 0])
    matrix.index = [f"{d:%Y-%m} (n={n})" for d, n in zip(retention.index, retention["cohort_size"])]
    fig, ax = plt.subplots(figsize=(11, 9))
    plotting.heatmap(matrix, "Cohort retention: % of cohort purchasing N months after first observed purchase", ax=ax, xlabel="Months since first purchase", ylabel="Cohort")
    plotting.save(fig, "cohort_retention")
    plt.close(fig)

    curve = average_retention_curve(retention)
    curve = curve[curve["months_since_first"] > 0]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    plotting.line_chart(curve, "months_since_first", "retention_pct", "Average repeat-purchase rate by months since first purchase", ax=ax)
    ax.set_ylim(0, curve["retention_pct"].max() * 1.3)
    ax.set_xlabel("Months since first observed purchase")
    plotting.percent(ax)
    plotting.save(fig, "retention_curve")
    plt.close(fig)


def churn_figures(churn: dict) -> None:
    curves = {name: (churn["y_test"], proba) for name, proba in churn["test_probabilities"].items()}
    fig = plotting.roc_pr_curves(curves, churn["base_rate_test"])
    plotting.save(fig, "churn_roc_pr")
    plt.close(fig)

    fig = plotting.confusion_matrix_plot(churn["chosen_metrics"], f"{churn['chosen_model']} — test set, threshold {churn['threshold']:.2f}")
    plotting.save(fig, "churn_confusion_matrix")
    plt.close(fig)

    fig = plotting.threshold_plot(churn["threshold_table"], churn["threshold"])
    plotting.save(fig, "churn_threshold_tradeoff")
    plt.close(fig)

    importance = churn["permutation_importance"].head(12)
    fig, ax = plt.subplots(figsize=(8, 5))
    plotting.barh_chart(importance, "feature", "importance_mean", f"Permutation importance — {churn['chosen_model']} (drop in test ROC-AUC)", fmt="{:.3f}", ax=ax)
    plotting.save(fig, "churn_feature_importance")
    plt.close(fig)


def segment_figures(segments: dict) -> None:
    fig = plotting.k_selection_plot(segments["k_evaluation"], segments["k"])
    plotting.save(fig, "segment_k_selection")
    plt.close(fig)

    profile = segments["profile"].set_index("segment")
    columns = ["days_since_last_purchase", "frequency_12m", "monetary_value_12m", "gross_margin_pct_12m", "avg_discount_pct_12m", "refund_rate_12m", "web_sessions_90d", "support_tickets_12m"]
    weights = profile["customers"]
    overall = (profile[columns].mul(weights, axis=0).sum() / weights.sum())
    indexed = 100 * profile[columns] / overall
    fig, ax = plt.subplots(figsize=(11, 0.6 * len(indexed) + 1.6))
    plotting.indexed_profile_heatmap(indexed, "Segment profiles (index: 100 = customer average; red above, blue below)", ax=ax)
    ax.set_xticks(range(len(columns)), [c.replace("_", " ") for c in columns], rotation=25, ha="right")
    plotting.save(fig, "segment_profiles")
    plt.close(fig)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 3.4))
    data = segments["profile"]
    plotting.barh_chart(data, "segment", "share_pct", "Share of customers", fmt="{:.1f}%", ax=ax1)
    plotting.barh_chart(data, "segment", "profit_share_pct", "Share of 12-month profit", fmt="{:.1f}%", ax=ax2)
    fig.tight_layout()
    plotting.save(fig, "segment_size_profit")
    plt.close(fig)


def main() -> None:
    plotting.apply_style()
    tables = load_raw_tables()
    snapshot = load_snapshot()
    frame = pipeline.load_model_frame(tables)

    print("1/5 Data-quality audit")
    audit = pipeline.run_quality_audit(tables, snapshot)
    (REPORTS_DIR / "data_quality_report.md").write_text(reporting.render_data_quality_report(audit, frame), encoding="utf-8")
    for name in ["overview", "primary_keys", "foreign_keys", "business_rules", "reconciliation", "outliers", "snapshot_reproduction"]:
        save_table(audit[name], f"dq_{name}")

    print("2/5 Business KPIs")
    business = pipeline.business_tables(tables)
    for name, value in business.items():
        if name in ("executive_summary", "repeat_purchase_rate_pct", "rfm"):
            continue
        save_table(value, name, index=(name == "cohort_retention"))
    headline = pipeline.headline_numbers(business)
    stats = pipeline.statistical_checks(tables, frame)
    business_figures(business)

    print("3/5 Churn model")
    churn = pipeline.run_churn_analysis(frame)
    save_table(churn["cv_results"], "churn_cv_results")
    save_table(churn["test_results"], "churn_test_results")
    save_table(churn["threshold_table"], "churn_threshold_table")
    save_table(churn["capacity_table"], "churn_capacity_table")
    save_table(churn["permutation_importance"], "churn_permutation_importance")
    save_table(churn["coefficients"], "churn_logistic_coefficients")
    churn_figures(churn)

    print("4/5 Segmentation")
    segments = pipeline.run_segmentation(frame)
    save_table(segments["k_evaluation"], "segment_k_evaluation")
    save_table(segments["profile"], "segment_profiles", index=True)
    segment_figures(segments)

    scores = pipeline.customer_scores(frame, churn, segments)
    save_table(scores, "customer_scores")

    print("5/5 Reports")
    metrics_json = {
        "disclaimer": "Synthetic data and synthetic churn label; metrics do not demonstrate real-world accuracy.",
        "executive_summary": business["executive_summary"],
        "repeat_purchase_rate_pct": business["repeat_purchase_rate_pct"],
        "headline": headline,
        "statistical_checks": stats,
        "churn": {
            "chosen_model": churn["chosen_model"],
            "threshold": churn["threshold"],
            "threshold_selection": "max F1 on out-of-fold training predictions",
            "base_rate_train": churn["base_rate_train"],
            "base_rate_test": churn["base_rate_test"],
            "test_metrics_at_threshold": churn["chosen_metrics"],
            "test_metrics_at_0_5": churn["default_threshold_metrics"],
            "cv_results": churn["cv_results"].to_dict(orient="records"),
        },
        "segmentation": {
            "k": segments["k"],
            "silhouette": float(segments["k_evaluation"].set_index("k").loc[segments["k"], "silhouette"]),
            "stability": segments["stability"],
            "segment_names": {str(k): v for k, v in segments["segment_names"].items()},
        },
    }
    (REPORTS_DIR / "model_metrics.json").write_text(json.dumps(metrics_json, indent=2, default=float), encoding="utf-8")
    (REPORTS_DIR / "business_recommendations.md").write_text(reporting.render_business_recommendations(business, headline, churn, segments, stats), encoding="utf-8")
    readme = PROJECT_ROOT / "README.md"
    try:
        reporting.update_marked_section(readme, "KEY-FINDINGS", reporting.render_key_findings(business, headline, churn, segments))
    except ValueError:
        print("README.md has no KEY-FINDINGS markers; skipped README update.")
    print("Done. Outputs written to reports/.")


if __name__ == "__main__":
    main()
