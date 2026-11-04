id: model-sql-1
stage: model
lang: sql
title: A regression line with SQL aggregates
--- task
SQL can fit a simple linear regression `monthly_spend = intercept + slope × income` with
aggregate functions. From **`customers`** return one row:

| column | function |
|---|---|
| `slope` | `regr_slope(y, x)` |
| `intercept` | `regr_intercept(y, x)` |
| `r2` | `regr_r2(y, x)` |
| `spend_at_60k` | predicted monthly spend for an income of 60,000 |

Note the argument order: **y first, then x**. How much does each extra 10,000 of income add to monthly spend?
--- starter
SELECT regr_slope(monthly_spend, income) AS slope
FROM customers;
--- solution
SELECT regr_slope(monthly_spend, income)                                   AS slope,
       regr_intercept(monthly_spend, income)                               AS intercept,
       regr_r2(monthly_spend, income)                                      AS r2,
       regr_intercept(monthly_spend, income) + 60000 * regr_slope(monthly_spend, income) AS spend_at_60k
FROM customers;
--- hints
- `regr_slope(monthly_spend, income)` - the target goes first.
- A prediction is `intercept + slope * x`.
