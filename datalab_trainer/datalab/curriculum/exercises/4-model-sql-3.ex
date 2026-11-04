id: model-sql-3
stage: model
lang: sql
title: Evaluate a rule-based churn score
level: 2
--- task
Before machine learning, try a simple business rule: flag a customer as **high risk** if
`support_calls >= 3 OR tenure_months < 6`.

Evaluate the rule against the real `churned` column. Return one row:

| column | definition |
|---|---|
| `tp` | flagged and churned (true positives) |
| `fp` | flagged but stayed |
| `fn` | not flagged but churned |
| `tn` | not flagged and stayed |
| `precision` | tp / (tp + fp), 3 dp |
| `recall` | tp / (tp + fn), 3 dp |

Is this rule useful? Compare precision with the overall churn rate.
--- starter
WITH scored AS (
    SELECT churned,
           CASE WHEN support_calls >= 3 THEN 1 ELSE 0 END AS flagged
    FROM customers
)
SELECT count(*) FILTER (WHERE flagged = 1 AND churned = 1) AS tp
FROM scored;
--- solution
WITH scored AS (
    SELECT churned,
           CASE WHEN support_calls >= 3 OR tenure_months < 6 THEN 1 ELSE 0 END AS flagged
    FROM customers
),
cm AS (
    SELECT count(*) FILTER (WHERE flagged = 1 AND churned = 1) AS tp,
           count(*) FILTER (WHERE flagged = 1 AND churned = 0) AS fp,
           count(*) FILTER (WHERE flagged = 0 AND churned = 1) AS fn,
           count(*) FILTER (WHERE flagged = 0 AND churned = 0) AS tn
    FROM scored
)
SELECT tp, fp, fn, tn,
       round(tp / (tp + fp), 3) AS precision,
       round(tp / (tp + fn), 3) AS recall
FROM cm;
--- hints
- `count(*) FILTER (WHERE ...)` for each cell of the confusion matrix.
- In DuckDB `/` on integers gives a decimal result, so tp / (tp + fp) works directly.
