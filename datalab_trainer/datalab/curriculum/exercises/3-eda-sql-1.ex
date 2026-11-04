id: eda-sql-1
stage: eda
lang: sql
title: Churn rate by plan
ordered: true
--- task
Using the clean view **`customers`**, return one row per `plan` with:

* `plan`
* `customers` – number of customers
* `churn_rate` – share who churned, **rounded to 3 decimals** (`churned` is 0/1, so its average is the rate)

Sort by `churn_rate` from highest to lowest. Which plan loses customers fastest?
--- starter
SELECT plan, count(*) AS customers
FROM customers
GROUP BY plan;
--- solution
SELECT plan,
       count(*)               AS customers,
       round(avg(churned), 3) AS churn_rate
FROM customers
GROUP BY plan
ORDER BY churn_rate DESC;
--- hints
- `avg(churned)` is the churn rate.
- Add `ORDER BY churn_rate DESC`.
