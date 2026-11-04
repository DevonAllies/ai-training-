id: report-sql-2
stage: report
lang: sql
title: A findings table with formatted numbers
ordered: true
--- task
Reports compare segments against the overall rate. Build a **findings table** for the report, one row per
segment of two kinds: `plan` and support-call band (`0-1`, `2-3`, `4+`):

| column | definition |
|---|---|
| `dimension` | `'plan'` or `'support calls'` |
| `segment` | e.g. `'Basic'`, `'4+'` |
| `customers` | count |
| `churn` | churn rate as text with a % sign and 1 decimal, e.g. `'30.9%'` (`printf('%.1f%%', …)`) |
| `vs_overall_pp` | difference from the overall churn rate in **percentage points**, 1 dp |

Sort by `dimension`, then by `vs_overall_pp` descending. Combine the two parts with `UNION ALL`.
--- starter
SELECT 'plan' AS dimension, plan AS segment, count(*) AS customers, avg(churned) AS churn
FROM customers
GROUP BY plan;
--- solution
WITH overall AS (SELECT avg(churned) AS r FROM customers),
seg AS (
    SELECT 'plan' AS dimension, plan AS segment, count(*) AS customers, avg(churned) AS rate
    FROM customers GROUP BY plan
    UNION ALL
    SELECT 'support calls',
           CASE WHEN support_calls <= 1 THEN '0-1' WHEN support_calls <= 3 THEN '2-3' ELSE '4+' END,
           count(*), avg(churned)
    FROM customers GROUP BY 2
)
SELECT dimension, segment, customers,
       printf('%.1f%%', 100 * rate)              AS churn,
       round(100 * (rate - overall.r), 1)        AS vs_overall_pp
FROM seg, overall
ORDER BY dimension, vs_overall_pp DESC;
--- hints
- Compute the overall rate in a one-row CTE and cross-join it.
- `printf('%.1f%%', 100 * rate)` formats a number as text; `%%` prints a literal %.
- In a `UNION ALL` the column names come from the first SELECT.
