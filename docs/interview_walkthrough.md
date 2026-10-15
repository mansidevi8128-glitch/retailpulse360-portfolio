# Interview Walkthrough — How to Present RetailPulse 360

This guide helps you explain the project clearly and honestly. Always say up front that it is a **portfolio project on synthetic data**, built with AI assistance, and not work done for a real company. Interviewers value this honesty, and it lets you focus on *how you think*, which is what an entry-level interview tests.

> Suggested framing: *"This is a self-directed portfolio project. The company, RetailPulse 360, is fictional and the data is synthetic, so I don't present the numbers as real business results. What I want to show is how I approach a business analytics problem end to end: checking the data, defining metrics correctly, analysing with SQL and Python, building a churn model and segments, and turning that into recommendations and a dashboard."*

Be ready to say which parts you understand deeply and which you are still learning. Re-run the notebooks yourself before interviews so you can explain every step in your own words.

---

## The 2-minute version (elevator pitch)

1. **Problem:** a fictional online retailer is growing fast but is worried about profitability, refunds, marketing efficiency and customer churn.
2. **Data:** seven tables (6,000 customers, about 30,000 orders, 56,000 order lines, 76,000 web sessions, 4,700 support tickets, monthly marketing spend), plus a customer snapshot with a churn label.
3. **What I did:** audited data quality, defined KPIs from how the data actually behaves, analysed it in PostgreSQL and Python, built a churn model and customer segments, made a Streamlit dashboard, and wrote recommendations. Everything is reproducible and tested.
4. **Three findings I would lead with:**
   - Growth is **volume-driven**: Jan–May 2026 revenue is about 65% above Jan–May 2025, while order value stayed flat at about $127–129.
   - **Paid acquisition looks very expensive**: paid social and search spend about $1,600 per new customer, against roughly $140 of first-year product profit per customer.
   - **Support is under strain**: tickets per 100 orders roughly doubled, and satisfaction drops sharply when a ticket takes more than 48 hours.
5. **Model:** a logistic regression ranks churn risk with a test ROC-AUC of about 0.79. The riskiest 20% of customers contain about 48% of churners. I am careful to say this is on a synthetic label.

## The 5-minute version (structure)

| Step | What to say | Evidence to show |
|---|---|---|
| 1. Data audit | "Before calculating anything, I checked keys, relationships and how money fields relate to order status." | `reports/data_quality_report.md` §4 table |
| 2. Metric definitions | "Refunded orders have zero revenue but keep their cost, so profit includes refund losses, AOV uses completed orders only, and refund rate is refunded ÷ (completed + refunded)." | `docs/metric_definitions.md` |
| 3. A data issue I found | "The snapshot's recency column uses `signup + 30 days` as a placeholder for 606 customers, including 289 who actually bought earlier. I replaced it with true recency and checked the model doesn't depend on it." | Notebook 02 §3 and §9 |
| 4. Key insight | "Marketing spend is larger than product-level profit, but the gap is narrowing as revenue grows. Paid channels cost about 11× first-year profit per customer, while customer quality is similar across channels." | channel unit-economics chart |
| 5. Model | "I compared three models with cross-validation, picked the simplest within 0.01 PR-AUC, chose the threshold on training data only, and translated scores into contact-capacity terms." | ROC/PR curves, capacity table |
| 6. Segments | "K-Means found four segments. I named them only after looking at the profiles, and I'm open that the separation is moderate (silhouette 0.23)." | segment heatmap |
| 7. Recommendations | "Every recommendation is a test, not a promise, because the data has no experiments." | `reports/business_recommendations.md` |

## The 15-minute version (deep dive with the dashboard)

1. **Open the dashboard** (`streamlit run dashboard/app.py`) and walk through the Executive summary tab. Point out the hover definitions on each KPI.
2. **Apply a filter** (for example, Region = West) and explain that KPIs are *recomputed* from filtered totals, not averaged, so ratios stay correct.
3. **Marketing tab:** cost per lead and spend per new customer. Explain the attribution caveat.
4. **Refunds & support tab:** margin falls with deeper discounts; satisfaction falls with slower resolution. Explain why these are associations, not proven causes.
5. **Segments tab:** the four segments and their profit share.
6. **Churn risk tab:** risk bands, the capacity curve, feature importance and the top-risk list. Explain *out-of-fold* scores: every customer is scored by a model that never saw that customer's label.
7. **Show one SQL file** (e.g. `sql/05_product_category_profitability.sql`) and explain how you avoided join fan-out.
8. **Show the tests** (`pytest`): data-quality expectations, KPI formulas on small examples, leakage checks, and SQL results matching pandas.
9. **Close with limitations** and what you would do with real data: more snapshots for time-based validation, cost data for CLV, and A/B tests.

## Numbers to remember (all from the executed analysis)

| Item | Value |
|---|---|
| Net revenue / profit (Jan 2024 – May 2026) | $3.64M / $1.42M (39.0% margin) |
| Completed orders / AOV | 28,436 / $128.12 |
| Refund rate | 4.2% of fulfilled orders |
| Jan–May 2026 vs 2025 revenue | +65.4% |
| Marketing spend (whole period) | $3.97M |
| Paid Social / Paid Search spend per new customer | $1,670 / $1,581 |
| Margin at 0% vs 21%+ discount | 40.8% vs 22.2% |
| Tickets per 100 orders (first vs last month) | 11.7 → 24.3 |
| Churn base rate | 26.7% |
| Churn model (Logistic Regression) | CV ROC-AUC 0.782; test ROC-AUC 0.785, PR-AUC 0.613 |
| At threshold 0.33 | precision 0.58, recall 0.57 |
| Top 20% riskiest | 64% precision, 48% of churners |
| Segments | k = 4, silhouette 0.23 |

If the pipeline is re-run, these values come from `reports/model_metrics.json` and the README findings block.

## What to say about AI assistance

Be honest: *"I used an AI assistant to help build and review parts of the project. I then worked through the notebooks, SQL and tests myself so that I can explain each decision."* Make sure that is true before you say it: open every notebook, change something, re-run it, and see what happens. Do not claim you wrote everything alone if you did not.

## Things not to say

- ❌ "I reduced churn by X%" or "this model will save $Y". There was no real deployment or experiment.
- ❌ "This is client data" or "I did this at a company".
- ❌ "The model is 80% accurate, so it works". Accuracy is the wrong metric here, and the label is synthetic.
- ✅ "On this synthetic dataset, the model ranks churn risk well enough to show the method. In a real setting I'd validate it over time and measure the effect of outreach with a control group."
