id: eda-sql-4
stage: eda
lang: sql
title: Correlations and percentiles in SQL
level: 2
--- task
Return **one row** describing the customers table:

| column | definition |
|---|---|
| `r_income_spend` | correlation between `income` and `monthly_spend` (3 dp) |
| `r_tenure_churn` | correlation between `tenure_months` and `churned` (3 dp) |
| `r_calls_churn` | correlation between `support_calls` and `churned` (3 dp) |
| `median_income` | median income |
| `p90_spend` | 90th percentile of monthly_spend (`quantile_cont`), 2 dp |

What do the signs of the churn correlations tell you?
--- starter
SELECT corr(income, monthly_spend) AS r_income_spend
FROM customers;
--- solution
SELECT round(corr(income, monthly_spend), 3)          AS r_income_spend,
       round(corr(tenure_months, churned), 3)         AS r_tenure_churn,
       round(corr(support_calls, churned), 3)         AS r_calls_churn,
       median(income)                                  AS median_income,
       round(quantile_cont(monthly_spend, 0.9), 2)    AS p90_spend
FROM customers;
--- hints
- `corr(x, y)` is an aggregate function, like `avg`.
- `quantile_cont(x, 0.9)` interpolates the 90th percentile.
