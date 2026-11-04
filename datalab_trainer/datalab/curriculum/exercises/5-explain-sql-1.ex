id: explain-sql-1
stage: explain
lang: sql
title: Shape a churn grid (pivot region × plan)
ordered: true
--- task
Readers find a grid easier than a long list. Return the churn rate (3 dp) with **one row
per region** and **one column per plan**, in this exact column order:

`region, Basic, Standard, Premium`

sorted by region. You can use DuckDB's `PIVOT` or conditional aggregation
(`avg(churned) FILTER (WHERE plan = 'Basic')`).
--- starter
SELECT region, plan, round(avg(churned), 3) AS churn_rate
FROM customers
GROUP BY region, plan
ORDER BY region, plan;
--- solution
SELECT region,
       round(avg(churned) FILTER (WHERE plan = 'Basic'), 3)    AS Basic,
       round(avg(churned) FILTER (WHERE plan = 'Standard'), 3) AS Standard,
       round(avg(churned) FILTER (WHERE plan = 'Premium'), 3)  AS Premium
FROM customers
GROUP BY region
ORDER BY region;
--- hints
- Conditional aggregation: `avg(churned) FILTER (WHERE plan = 'Basic') AS Basic`
- With PIVOT: `SELECT region, Basic, Standard, Premium FROM (PIVOT customers ON plan USING round(avg(churned), 3) GROUP BY region) ORDER BY region`
