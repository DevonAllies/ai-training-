id: basics-sql-2
stage: basics
lang: sql
title: GROUP BY and HAVING
--- task
For each `region` return:

* `region`
* `customers` – number of customers (`count(*)`)
* `avg_age` – average age, rounded to 1 decimal
* `max_spend` – highest `monthly_spend`

but only for regions with **more than 140 customers** (use `HAVING`).
--- starter
SELECT region, count(*) AS customers
FROM customers
GROUP BY region;
--- solution
SELECT region,
       count(*)           AS customers,
       round(avg(age), 1) AS avg_age,
       max(monthly_spend) AS max_spend
FROM customers
GROUP BY region
HAVING count(*) > 140;
--- hints
- Every column in SELECT is either in GROUP BY or inside an aggregate function.
- `HAVING count(*) > 140` goes after GROUP BY.
