id: report-sql-1
stage: report
lang: sql
title: A KPI table to quote in the report
--- task
Executive summaries quote a few headline numbers. Produce them **with code**, in one row:

| column | definition |
|---|---|
| `customers` | number of customers |
| `churn_pct` | churn rate in percent, 1 dp |
| `avg_spend` | average monthly spend, 2 dp |
| `revenue_2024` | total order revenue in 2024, rounded to whole units |
| `top_category_2024` | category with the most revenue in 2024 |

Tip: compute each piece in its own CTE and cross-join them.
--- starter
WITH c AS (
    SELECT count(*) AS customers
    FROM customers
)
SELECT * FROM c;
--- solution
WITH c AS (
    SELECT count(*)                         AS customers,
           round(100 * avg(churned), 1)     AS churn_pct,
           round(avg(monthly_spend), 2)     AS avg_spend
    FROM customers
),
o AS (
    SELECT category, sum(quantity * unit_price * (1 - discount)) AS revenue
    FROM orders
    WHERE year(order_date) = 2024
    GROUP BY category
)
SELECT c.customers, c.churn_pct, c.avg_spend,
       (SELECT round(sum(revenue)) FROM o)                        AS revenue_2024,
       (SELECT category FROM o ORDER BY revenue DESC LIMIT 1)     AS top_category_2024
FROM c;
--- hints
- `year(order_date) = 2024` filters a year.
- A scalar sub-query `(SELECT ... LIMIT 1)` can be used as a column.
