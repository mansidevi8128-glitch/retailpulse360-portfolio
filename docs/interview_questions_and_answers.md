# Interview Questions & Answers — RetailPulse 360

The answers are grounded in what this project actually implemented. Rephrase them in your own words. Remember that the data is synthetic and the project is a self-directed, AI-assisted portfolio piece, not professional experience.

---

## A. Project and business understanding

**1. Tell me about this project.**
It's an end-to-end analytics case study for a fictional online retailer, RetailPulse 360, built on synthetic data. I audited the data, defined KPIs, analysed sales, marketing, refunds, support and retention with SQL and Python, built a churn model and customer segments, made a Streamlit dashboard, and wrote recommendations. The emphasis is on correct metric definitions and reproducibility: one script regenerates every number, and tests check the logic.

**2. What was the most important business finding?**
Recorded marketing spend ($3.97M) was larger than product-level profit ($1.42M) over the period. Paid Social and Paid Search cost about $1,600 per new customer, while first-year profit per customer was around $140 in every channel. So paid acquisition doesn't pay back within a year at those costs, and customer quality is similar across channels. The gap is narrowing because revenue grew while spend stayed flat. I'd recommend holdout tests before moving budget, because single-touch attribution can't show incremental impact.

**3. Is the business growing because customers spend more or because there are more customers?**
More customers. Comparing January–May 2026 with January–May 2025, revenue rose about 65% and purchasing customers about 60%, while AOV moved from $128.59 to $126.64. I compared the same months because 2026 only has five months of data.

**4. What would you tell the CEO in one sentence?**
"We're growing by adding customers, not basket size; our paid acquisition and discounting are expensive relative to the profit customers generate; and support quality is at risk as volume grows — let's run controlled tests on spend, discounts and retention outreach before scaling any of them."

## B. Data quality

**5. How did you check data quality?**
Row counts against the documentation; data types and date ranges; missing values and duplicate rows; primary-key uniqueness, including the composite key `month + channel` for marketing; foreign-key orphans; business rules such as orders before sign-up or conversions without checkout; and outliers with a 3 × IQR rule. All of these are reusable functions in `quality.py` with tests. The data was clean structurally, with zero orphans and zero missing values, but I found three semantic issues.

**6. What issues did you find?**
(1) In the modeling snapshot, `recency_days` was a placeholder (`signup + 30 days`) for 606 customers without a recent purchase, including 289 who did buy earlier. (2) CSAT was imputed as 4.0 for customers without tickets. (3) 4,079 orders had a coupon flag but a 0% discount. I didn't overwrite anything. I added corrected columns, documented assumptions, and tested that the model doesn't depend on the placeholder.

**7. How do you distinguish duplicates from legitimate repeated keys?**
A customer appearing in many orders is expected. That's a one-to-many relationship. I only treat repeats as duplicates when the *primary key* repeats or when an entire row is identical. For marketing, month and channel each repeat, but the pair `(month, channel)` is unique.

**8. How did you decide how to calculate revenue and profit?**
I tested hypotheses against the data instead of assuming. For completed orders, net revenue equals GMV plus the shipping fee, with zero exceptions. Refunded orders have zero revenue but keep their merchandise cost, so their profit is negative. Cancelled orders are all zeros. That's why AOV divides by completed orders only, refund rate uses completed + refunded as its denominator, and GMV is described as demand rather than revenue.

## C. SQL

**9. What is join fan-out, and how did you avoid it?**
When you join a "one" table (orders) to a "many" table (order items), each order row repeats once per line. Summing an order-level column like `net_revenue_usd` after that join double-counts it. I avoided it by aggregating line items to order grain in a CTE before joining, and by using line-level columns (`line_revenue_usd`) for category analysis. In the customer feature view, each source (orders, sessions, tickets) is aggregated per customer in its own CTE before the final join.

**10. Which window functions did you use and why?**
`LAG` for month-over-month and year-over-year growth and for days between orders; `NTILE(5)` for RFM scores; `RANK` and `ROW_NUMBER` to rank categories and pick the top 3 products per category; and `SUM() OVER ()` for shares of total.

**11. How did you build cohort retention in SQL?**
I took each customer's first completed-order month as their cohort, computed months since the cohort for every later order month, counted distinct active customers per cohort and month, and divided by cohort size. For the average curve I used `generate_series` to include only cohorts old enough to be observed at month N, so recent cohorts don't drag the average down.

**12. How do you know your SQL is correct?**
I ran every script on PostgreSQL 16, and a pytest test rebuilds the database and compares the SQL results with the pandas implementation: monthly revenue and profit, category profit, first-year value, cohort retention, and a zero-mismatch rebuild of all snapshot features.

## D. Python and engineering

**13. Why put code in `src/` instead of only in notebooks?**
So that every number has one definition. The notebooks, the report script, the dashboard and the tests all import the same functions, so the dashboard can't silently disagree with the report. It also makes the logic testable.

**14. What do your tests cover?**
Data expectations (row counts, keys, reconciliation); KPI formulas on small examples I can check by hand; join fan-out; leakage safeguards (adding a future order must not change any feature; the target can't be used as a feature); modeling (the scaler is fitted on training data only, the split is stratified); segmentation rules; the generated reports; SQL against pandas; and a headless dashboard run.

**15. How would someone reproduce your results?**
`pip install -r requirements.txt`, `pip install -e .`, then `python scripts/run_pipeline.py`. Seeds are fixed (42) and paths are relative to the repository root. Notebooks re-run with `jupyter nbconvert --execute`.

## E. Dashboard

**16. How did you avoid misleading KPIs in the dashboard?**
Every ratio is recomputed from filtered totals: AOV = filtered revenue ÷ filtered completed orders, never an average of monthly AOVs. Filters that can't apply to a dataset are explained (marketing has no region). Model outputs are labelled as model-derived and synthetic. Magnitude axes start at zero, and each KPI has a definition tooltip.

**17. Why Streamlit instead of Power BI?**
Streamlit let me build a working, testable dashboard in Python on top of the same metric functions. I also wrote a Power BI build guide with the star schema and DAX measures, but I didn't include a `.pbix` file because I couldn't create and verify one in the build environment.

## F. Churn model

**18. How did you define churn, and is the label reliable?**
The label `churned_next_90d` was provided with the dataset. It's synthetic, generated from risk signals plus noise, and I can't verify it from the transactions because the order data ends on the snapshot date. So I treat model performance as a demonstration of the method, not a real-world accuracy claim.

**19. How did you prevent data leakage?**
Four ways. (1) I rebuilt every feature from events on or before the snapshot date and matched the provided values 100%; a test also adds a future order and checks that nothing changes. (2) IDs, the target and the snapshot date are blocked by a guard function. (3) I checked single-feature AUCs: the best was about 0.77, nowhere near the 1.0 that would suggest a leaked label. (4) All preprocessing is inside scikit-learn Pipelines, so scaling and encoding are fitted only on training folds.

**20. Why logistic regression?**
I compared it with a Random Forest and gradient boosting using 5-fold cross-validation. Logistic regression had the best CV ROC-AUC (0.782) and PR-AUC. My rule was to prefer the simpler model if it's within 0.01 PR-AUC of the best, because it's easier to explain and maintain. The tree models adding nothing suggests the signal is mostly additive.

**21. Why not use accuracy?**
About 27% of customers churn, so predicting "nobody churns" is 73% accurate and useless. I used ROC-AUC for ranking quality, PR-AUC compared with the 27% base rate, and precision, recall and F1 at a chosen threshold.

**22. How did you choose the threshold?**
I maximised F1 on out-of-fold predictions from the *training* set (0.33) and then applied it once to the test set: precision 0.58, recall 0.57. In practice the threshold should come from costs: the cost of contacting a customer against the value of saving one. Those aren't in the data, so I also gave a capacity table, for example "contact the riskiest 20% and reach about 48% of churners at 64% precision". The capacity levels are labelled as assumptions.

**23. What drives churn in your model?**
Time since the last purchase dominates permutation importance, followed by purchase frequency and whether the customer has ever purchased. Loyalty tier, refund rate and CSAT add a little. I used permutation importance because frequency, monetary value and profit are highly correlated (r ≈ 0.83–0.98), which makes individual logistic coefficients unstable.

**24. What did the error analysis show?**
Missed churners (false negatives) look like active customers, with recent purchases and decent frequency, so the available features can't separate them. Part of that is the noise built into the synthetic label. False positives look like churners (long inactivity) but stayed. Those are the customers where a retention offer might be wasted.

**25. Would you deploy this model?**
Not as is. I'd need several historical snapshots for out-of-time validation, monitoring for drift and calibration, confirmation that attributes like loyalty tier were known at prediction time, and a randomised holdout to measure whether outreach actually reduces churn. A churn score predicts risk; it doesn't tell you who will respond to an offer.

## G. Segmentation

**26. How did you choose features for clustering?**
RFM (true recency, 12-month frequency and value) plus margin, discount, refund rate, 90-day web sessions and support tickets. I left out profit, AOV and category diversity because they're highly correlated with value and frequency and would give that dimension too much weight. I used them only to describe the segments. The churn label is never a clustering input, and a test enforces this.

**27. Why transform and scale?**
K-Means uses distances, so skewed variables and different units (dollars against counts) would dominate. I applied `log1p` to skewed counts and amounts and then standardised every feature.

**28. How did you choose k = 4?**
I compared inertia and silhouette for k = 2 to 8. k = 2 had the best silhouette but only split off customers with no recent purchase, which we already know. My rule was the highest silhouette with k ≥ 3 and no cluster smaller than 5% of customers, which gave k = 4. The silhouette is about 0.23, which is moderate, so I describe the segments as useful summaries rather than natural groups. Seeds gave identical results; bootstrap stability averaged an adjusted Rand index of 0.85.

**29. Describe the segments.**
Promotion-Driven Frequent Buyers (42%): the highest frequency and value and twice the average discount; 57% of profit and the lowest churn. Full-Price Regulars (43%): almost no discounts and the highest margin, but buy less often. Lapsed / No Recent Purchase (9%): no purchase in 12 months, about half never bought, 64% churn. Refund-Prone Buyers (5%): about half their orders refunded, 47% churn.

**30. What would you do for each segment?**
Test loyalty rewards in place of percentage discounts for the promotion buyers, carefully, because they're the most valuable. Use frequency nudges for full-price regulars. Run low-cost win-back and onboarding offers for lapsed customers. Fix product root causes for refund-prone buyers. Each one is a test with a control group.

## H. Interpretation and judgement

**31. Marketplace orders have a higher refund rate. Is that a finding?**
Not yet. It's 5.0% against 4.2% on the website, but a chi-square test gives p ≈ 0.07, so I report it as a hypothesis to monitor, not a conclusion.

**32. What's the difference between correlation and causation in your findings?**
Deeper discounts are associated with lower margin. That part is arithmetic. But I can't say discounts *create* sales without an experiment. Likewise, slow ticket resolution is associated with low CSAT, but the slow tickets might also be the harder problems. That's why the recommendations are framed as tests.

**33. What would you do with more time or real data?**
Add shipping, fulfilment and support costs to compute contribution margin and CLV; build monthly snapshots for time-based model validation; link tickets and sessions to orders; run A/B tests on spend, discounts and outreach; and schedule the pipeline so the dashboard refreshes automatically.

**34. What was hardest, and what did you learn?**
Getting the definitions right before analysing. For example, discovering that refunded orders keep their cost, and that the recency column contained a placeholder. I learned to test assumptions against the data, aggregate at the right grain before joining, and be explicit about what the data can and can't prove.

**35. How much of this did you do yourself?**
Answer honestly. For example: "I used an AI assistant to help build and review the project, and I've worked through every notebook, SQL script and test so that I can explain and modify them." Only say this if it's true.
