id: explain-sql-2
stage: explain
lang: sql
title: SHAP values of a one-feature model in SQL
ordered: true
--- task
For a linear model `spend = intercept + slope × income`, the SHAP value of income for a
customer is

```
φ_income = slope × (income − average income)
```

i.e. how far that customer's income pushes the prediction away from the average prediction.

Return the **5 customers with the largest positive φ_income**, with columns
`customer_id`, `income`, `phi_income` (2 dp), sorted by `phi_income` descending
(break ties by `customer_id`).
--- starter
WITH m AS (
    SELECT regr_slope(monthly_spend, income) AS slope,
           avg(income)                       AS mean_income
    FROM customers
)
SELECT customer_id, income
FROM customers
LIMIT 5;
--- solution
WITH m AS (
    SELECT regr_slope(monthly_spend, income) AS slope,
           avg(income)                       AS mean_income
    FROM customers
)
SELECT c.customer_id,
       c.income,
       round(m.slope * (c.income - m.mean_income), 2) AS phi_income
FROM customers c, m
ORDER BY phi_income DESC, customer_id
LIMIT 5;
--- hints
- Join the one-row CTE to every customer with `FROM customers c, m` (a cross join).
- `ORDER BY phi_income DESC, customer_id LIMIT 5`
