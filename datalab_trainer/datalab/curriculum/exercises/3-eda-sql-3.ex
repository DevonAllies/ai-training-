id: eda-sql-3
stage: eda
lang: sql
title: Segment by support calls
ordered: true
--- task
Do customers who phone support more often churn more?

Put customers into bands by `support_calls`: **`0-1`**, **`2-3`** and **`4+`**, and return:

* `call_band`
* `customers`
* `churn_rate` (rounded to 3 decimals)

ordered `0-1`, `2-3`, `4+`.
--- starter
SELECT support_calls, count(*) AS customers, avg(churned) AS churn_rate
FROM customers
GROUP BY support_calls
ORDER BY support_calls;
--- solution
SELECT CASE WHEN support_calls <= 1 THEN '0-1'
            WHEN support_calls <= 3 THEN '2-3'
            ELSE '4+' END       AS call_band,
       count(*)                 AS customers,
       round(avg(churned), 3)   AS churn_rate
FROM customers
GROUP BY call_band
ORDER BY call_band;
--- hints
- `CASE WHEN ... THEN ... WHEN ... THEN ... ELSE ... END AS call_band`
- The text labels '0-1' < '2-3' < '4+' already sort correctly.
