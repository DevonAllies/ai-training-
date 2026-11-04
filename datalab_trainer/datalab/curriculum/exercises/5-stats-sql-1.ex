id: stats-sql-1
stage: stats
lang: sql
title: Confidence intervals for churn rates
--- task
For each `plan` return:

| column | definition |
|---|---|
| `plan` | |
| `n` | customers |
| `churn_rate` | proportion who churned, 3 dp |
| `lower_95`, `upper_95` | 95% confidence interval: `p ± 1.96 × sqrt(p(1−p)/n)`, 3 dp |

Do the intervals of Basic and Premium overlap? What does that suggest?
--- starter
SELECT plan, count(*) AS n, avg(churned) AS churn_rate
FROM customers
GROUP BY plan;
--- solution
WITH s AS (
    SELECT plan, count(*) AS n, avg(churned) AS p
    FROM customers
    GROUP BY plan
)
SELECT plan,
       n,
       round(p, 3)                               AS churn_rate,
       round(p - 1.96 * sqrt(p * (1 - p) / n), 3) AS lower_95,
       round(p + 1.96 * sqrt(p * (1 - p) / n), 3) AS upper_95
FROM s;
--- hints
- Compute `n` and `p` per plan in a CTE, then use them in the formula.
- `sqrt()` is the square root.
