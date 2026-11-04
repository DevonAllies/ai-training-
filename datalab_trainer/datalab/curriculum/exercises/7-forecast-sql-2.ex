id: forecast-sql-2
stage: forecast
lang: sql
title: Evaluate baseline forecasts in SQL
--- task
Hold out the **last 52 weeks** as the test set (`week >= DATE '2024-01-08'`); everything before is training data.

Compute the **MAE** (mean absolute error) on the test weeks of three baselines, as one row with
columns `mae_naive`, `mae_seasonal`, `mae_seasonal_growth` (all rounded to 0 dp):

* **naive** – every test week = the last training week's sales
* **seasonal** – each test week = sales 52 weeks earlier (`lag(sales, 52)`)
* **seasonal_growth** – seasonal × growth, where growth = (sum of the last 52 training weeks) / (sum of the 52 weeks before those)

Which baseline would you show finance, and why?
--- starter
WITH f AS (
    SELECT week, sales, lag(sales, 52) OVER (ORDER BY week) AS seasonal
    FROM store_sales
)
SELECT avg(abs(sales - seasonal)) AS mae_seasonal
FROM f
WHERE week >= DATE '2024-01-08';
--- solution
WITH numbered AS (
    SELECT week, sales,
           lag(sales, 52) OVER (ORDER BY week) AS seasonal,
           row_number() OVER (ORDER BY week)   AS i
    FROM store_sales
),
train AS (SELECT * FROM numbered WHERE week < DATE '2024-01-08'),
p AS (
    SELECT (SELECT sales FROM train ORDER BY week DESC LIMIT 1) AS last_value,
           (SELECT sum(sales) FROM train WHERE i > (SELECT max(i) FROM train) - 52) /
           (SELECT sum(sales) FROM train WHERE i <= (SELECT max(i) FROM train) - 52
                                          AND i > (SELECT max(i) FROM train) - 104) AS growth
)
SELECT round(avg(abs(n.sales - p.last_value)))          AS mae_naive,
       round(avg(abs(n.sales - n.seasonal)))            AS mae_seasonal,
       round(avg(abs(n.sales - n.seasonal * p.growth))) AS mae_seasonal_growth
FROM numbered n, p
WHERE n.week >= DATE '2024-01-08';
--- hints
- Number the weeks with `row_number() OVER (ORDER BY week)` so you can pick "the last 52 training weeks" by position.
- Put the last training value and the growth factor in a one-row CTE and cross-join it.
- MAE is `avg(abs(actual - forecast))`.
