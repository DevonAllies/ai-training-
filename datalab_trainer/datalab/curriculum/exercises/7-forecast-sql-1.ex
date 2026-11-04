id: forecast-sql-1
stage: forecast
lang: sql
title: Moving averages and year-over-year growth
ordered: true
--- task
Using window functions on **`store_sales`**, return the **last 8 weeks** of 2024 with:

* `week`, `sales`
* `ma4` – average of this week and the 3 previous weeks, rounded to 0 dp
* `last_year` – sales in the same week one year (52 weeks) earlier
* `yoy_pct` – year-over-year growth in percent: `100 * (sales / last_year - 1)`, 1 dp

ordered by `week`.
--- starter
SELECT week, sales,
       avg(sales) OVER (ORDER BY week) AS ma4
FROM store_sales
ORDER BY week;
--- solution
WITH w AS (
    SELECT week,
           sales,
           round(avg(sales) OVER (ORDER BY week ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)) AS ma4,
           lag(sales, 52) OVER (ORDER BY week)                                               AS last_year
    FROM store_sales
)
SELECT week, sales, ma4, last_year,
       round(100 * (sales / last_year - 1), 1) AS yoy_pct
FROM w
ORDER BY week
OFFSET (SELECT count(*) - 8 FROM store_sales);
--- hints
- A frame: `avg(sales) OVER (ORDER BY week ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)`.
- `lag(sales, 52) OVER (ORDER BY week)` looks 52 rows back.
- Compute the windows in a CTE *before* keeping only the last 8 rows, otherwise the windows can't see earlier weeks.
