id: visualise-sql-2
stage: visualise
lang: sql
title: Chart-ready data - revenue share by category per year
--- task
For a **100% stacked bar chart** you need each category's *share* of the year's revenue.

From `orders` return `year`, `category`, `revenue` (2 dp) and `share_pct` (share of that year's
total revenue, 1 dp). Revenue is `quantity * unit_price * (1 - discount)`. Each year's shares should add up to about 100.
--- starter
SELECT year(order_date) AS year, category,
       sum(quantity * unit_price * (1 - discount)) AS revenue
FROM orders
GROUP BY ALL;
--- solution
WITH yearly AS (
    SELECT year(order_date)                                       AS year,
           category,
           sum(quantity * unit_price * (1 - discount))            AS revenue
    FROM orders
    GROUP BY ALL
)
SELECT year,
       category,
       round(revenue, 2)                                          AS revenue,
       round(100 * revenue / sum(revenue) OVER (PARTITION BY year), 1) AS share_pct
FROM yearly;
--- hints
- Aggregate per year and category in a CTE first, then `sum(revenue) OVER (PARTITION BY year)` is the year total.
- `GROUP BY ALL` groups by every non-aggregated column.
