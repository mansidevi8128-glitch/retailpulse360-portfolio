# Project Brief

## Company
RetailPulse 360 (fictional) is a U.S. omnichannel e-commerce retailer.

## Scenario
The company has grown quickly but leadership is worried about uneven profitability, refund behavior, marketing efficiency and customer retention.

## Your role
You are the Data Analyst assigned to build an executive-ready analytics solution and a customer intelligence layer.

## Core business questions
1. How are revenue, profit, AOV, orders and customers trending month over month?
2. Which product categories and U.S. regions contribute the most revenue and profit?
3. Which acquisition channels generate valuable customers, not just traffic?
4. What behaviors are associated with refunds and support burden?
5. What is the repeat-purchase and retention pattern?
6. Can we predict which customers are likely to churn in the next 90 days?
7. Can we segment customers into actionable groups using behavioral/value features?
8. What actions would improve retention, margin and marketing allocation?

## Supervised-learning task
Target: `churned_next_90d`
Suggested baseline: Logistic Regression
Suggested comparison: Random Forest / Gradient Boosting
Primary evaluation: ROC-AUC + Precision/Recall + confusion matrix
Business emphasis: identify high-risk customers without overwhelming the retention team.

## Unsupervised-learning task
Build customer segments using RFM + engagement + profitability/support features.
Suggested models: K-Means; optionally compare with hierarchical clustering.
Validation: elbow curve, silhouette score, cluster stability/business interpretability.

## Final business deliverable
An executive dashboard + concise recommendation memo that connects descriptive analytics, churn risk, and customer segments.
