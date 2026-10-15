# Power BI Build Guide

This guide describes how to rebuild the RetailPulse 360 dashboard in Power BI Desktop. **No `.pbix` file is included**, because one could not be created and verified in this project's build environment. The Streamlit dashboard (`dashboard/app.py`) is the working, tested version. The measures below follow `docs/metric_definitions.md`, so both tools report the same numbers.

> Synthetic data disclosure: put a text box on every page stating that RetailPulse 360 is fictional and the data is synthetic.

## 1. Load data

Get Data → Text/CSV, and load these files:

| File | Table name |
|---|---|
| `data/raw/customers.csv` | Customers |
| `data/raw/products.csv` | Products |
| `data/raw/orders.csv` | Orders |
| `data/raw/order_items.csv` | OrderItems |
| `data/raw/web_sessions.csv` | Sessions |
| `data/raw/support_tickets.csv` | Tickets |
| `data/raw/marketing_spend.csv` | Marketing |
| `reports/tables/customer_scores.csv` | CustomerScores (segments + out-of-fold churn scores) |

In Power Query, set the date columns to *Date*, money columns to *Fixed decimal number*, and IDs to *Text*.

Create a **Date** table (DAX):

```DAX
Date =
ADDCOLUMNS (
    CALENDAR ( DATE ( 2023, 1, 1 ), DATE ( 2026, 5, 31 ) ),
    "Year", YEAR ( [Date] ),
    "Month", FORMAT ( [Date], "MMM yyyy" ),
    "MonthStart", DATE ( YEAR ( [Date] ), MONTH ( [Date] ), 1 ),
    "MonthNumber", MONTH ( [Date] )
)
```

Mark it as a date table. Sort `Month` by `MonthStart`.

## 2. Relationships (star schema)

| From (many) | To (one) | Cardinality | Filter direction |
|---|---|---|---|
| Orders[customer_id] | Customers[customer_id] | many-to-one | single |
| OrderItems[order_id] | Orders[order_id] | many-to-one | single |
| OrderItems[product_id] | Products[product_id] | many-to-one | single |
| Sessions[customer_id] | Customers[customer_id] | many-to-one | single |
| Tickets[customer_id] | Customers[customer_id] | many-to-one | single |
| CustomerScores[customer_id] | Customers[customer_id] | one-to-one | single |
| Orders[order_date] | Date[Date] | many-to-one | single |
| Sessions[session_date] | Date[Date] | many-to-one | single |
| Tickets[opened_date] | Date[Date] | many-to-one | single |
| Marketing[month] | Date[Date] | many-to-one | single |

Marketing has no customer key. Do **not** relate it to Customers. To filter it by channel, create a small `Channel` dimension (the six channel names) and relate both `Marketing[channel]` and `Customers[acquisition_channel]` to it.

For category analysis, add a calculated column to OrderItems so line measures can respect order status without a bidirectional relationship:

```DAX
OrderItems[order_status] = RELATED ( Orders[order_status] )
```

## 3. Measures

```DAX
Net Revenue = SUM ( Orders[net_revenue_usd] )
GMV = SUM ( Orders[gross_merchandise_value_usd] )
Profit = SUM ( Orders[profit_usd] )
Profit Margin % = DIVIDE ( [Profit], [Net Revenue] )

Orders Placed = COUNTROWS ( Orders )
Completed Orders = CALCULATE ( COUNTROWS ( Orders ), Orders[order_status] = "Completed" )
Refunded Orders = CALCULATE ( COUNTROWS ( Orders ), Orders[order_status] = "Refunded" )
Cancelled Orders = CALCULATE ( COUNTROWS ( Orders ), Orders[order_status] = "Cancelled" )

AOV = DIVIDE ( [Net Revenue], [Completed Orders] )
Refund Rate % = DIVIDE ( [Refunded Orders], [Completed Orders] + [Refunded Orders] )
Cancellation Rate % = DIVIDE ( [Cancelled Orders], [Orders Placed] )
Refund Loss = - CALCULATE ( [Profit], Orders[order_status] = "Refunded" )

Purchasing Customers =
CALCULATE ( DISTINCTCOUNT ( Orders[customer_id] ), Orders[order_status] = "Completed" )

Revenue MoM % =
VAR CurrentRevenue = [Net Revenue]
VAR PreviousRevenue = CALCULATE ( [Net Revenue], DATEADD ( 'Date'[Date], -1, MONTH ) )
RETURN DIVIDE ( CurrentRevenue - PreviousRevenue, PreviousRevenue )

-- Category (line grain): revenue only on completed lines; cost on completed + refunded lines
Category Revenue = CALCULATE ( SUM ( OrderItems[line_revenue_usd] ), OrderItems[order_status] = "Completed" )
Category Cost = CALCULATE ( SUM ( OrderItems[line_cost_usd] ), OrderItems[order_status] IN { "Completed", "Refunded" } )
Category Profit = [Category Revenue] - [Category Cost]
Category Margin % = DIVIDE ( [Category Profit], [Category Revenue] )

Marketing Spend = SUM ( Marketing[spend_usd] )
CTR % = DIVIDE ( SUM ( Marketing[clicks] ), SUM ( Marketing[impressions] ) )
Cost per Lead = DIVIDE ( [Marketing Spend], SUM ( Marketing[leads] ) )

Session Conversion % = DIVIDE ( SUM ( Sessions[converted] ), COUNTROWS ( Sessions ) )
Tickets = COUNTROWS ( Tickets )
Avg CSAT = AVERAGE ( Tickets[csat_score] )
Satisfied % = DIVIDE ( CALCULATE ( COUNTROWS ( Tickets ), Tickets[csat_score] >= 4 ), [Tickets] )
Tickets per 100 Orders = DIVIDE ( [Tickets], [Completed Orders] + [Refunded Orders] ) * 100

Avg Churn Score = AVERAGE ( CustomerScores[churn_probability] )
Observed Churn % = AVERAGE ( CustomerScores[churned_next_90d] )
```

**Important:** never use `SUM` on `Orders` columns inside a visual whose rows come from `OrderItems` (for example, a category axis). The relationship would repeat order values for each line. Use the line-grain category measures instead.

## 4. Report pages

| Page | Visuals |
|---|---|
| **1. Executive overview** | KPI cards (Net Revenue, Profit, Margin %, Completed Orders, AOV, Refund Rate %, GMV, Marketing Spend); line chart of Net Revenue and Profit by `Date[MonthStart]`; line chart of Purchasing Customers; slicers for Month range, Region, Acquisition Channel and Sales Channel |
| **2. Products & regions** | bar charts of Category Profit and Category Margin %; matrix Category × Year; bar chart of Net Revenue per customer by Region; sales-channel table |
| **3. Marketing** | bar charts of Cost per Lead and Spend per New Customer by channel; spend trend line; table of channel efficiency; a text box explaining that attribution is single-touch |
| **4. Retention** | purchase-frequency column chart; cohort matrix (rows = first purchase month, columns = months since first purchase; build with a calculated cohort column or import `reports/tables/cohort_retention.csv`) |
| **5. Refunds & support** | Profit Margin % and Refund Rate % by discount band; tickets per 100 orders trend; Satisfied % by resolution band; table by issue type |
| **6. Segments & churn risk** | customers and profit by segment; observed churn by segment; risk-band distribution; top-N risk table. Add the label "Model-derived on a synthetic churn label". |

Formatting: one accent colour for single-series visuals, a consistent colour per category across pages, a zero baseline for magnitudes, tooltips that show the measure definition, and no dual-axis charts.

## 5. Validation checklist

With no filters applied, compare the cards with `reports/model_metrics.json` → `executive_summary`. They should match exactly: Net Revenue $3,643,299.56; Profit $1,422,054.32; Completed Orders 28,436; AOV $128.12; Refund Rate 4.22%.
