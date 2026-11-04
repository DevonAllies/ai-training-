id: stats-sql-2
stage: stats
lang: sql
title: A two-proportion z-test in SQL
--- task
Test whether **Basic** customers churn more than **Premium** customers.

Return one row:

| column | definition |
|---|---|
| `p_basic`, `p_premium` | churn rates (4 dp) |
| `diff` | p_basic − p_premium (4 dp) |
| `p_pooled` | churn rate of both groups combined (4 dp) |
| `z` | `diff / sqrt(p_pooled × (1 − p_pooled) × (1/n_basic + 1/n_premium))`, 2 dp |

A |z| above 1.96 means p < 0.05 (two-sided).
--- starter
SELECT avg(churned) FILTER (WHERE plan = 'Basic')   AS p_basic,
       avg(churned) FILTER (WHERE plan = 'Premium') AS p_premium
FROM customers;
--- solution
WITH g AS (
    SELECT avg(churned) FILTER (WHERE plan = 'Basic')     AS p1,
           count(*)     FILTER (WHERE plan = 'Basic')     AS n1,
           avg(churned) FILTER (WHERE plan = 'Premium')   AS p2,
           count(*)     FILTER (WHERE plan = 'Premium')   AS n2,
           avg(churned) FILTER (WHERE plan IN ('Basic', 'Premium')) AS pp
    FROM customers
)
SELECT round(p1, 4)       AS p_basic,
       round(p2, 4)       AS p_premium,
       round(p1 - p2, 4)  AS diff,
       round(pp, 4)       AS p_pooled,
       round((p1 - p2) / sqrt(pp * (1 - pp) * (1.0 / n1 + 1.0 / n2)), 2) AS z
FROM g;
--- hints
- `avg(churned) FILTER (WHERE plan = 'Basic')` and `count(*) FILTER (...)` give each group's rate and size.
- The pooled rate uses only the Basic and Premium customers.
