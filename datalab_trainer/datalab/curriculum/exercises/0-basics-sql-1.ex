id: basics-sql-1
stage: basics
lang: sql
title: SELECT, WHERE, ORDER BY
ordered: true
--- task
Find Ridgeway's biggest-spending **Premium customers in the North region**.

From the `customers` table return `customer_id`, `name` and `monthly_spend` for customers who are on the
`Premium` plan **and** in the `North` region **and** spend **more than 100** per month,
sorted from the highest spender to the lowest.

Run `SELECT * FROM customers LIMIT 5` first to see the columns.
--- starter
SELECT customer_id, name, monthly_spend
FROM customers
WHERE plan = 'Premium'
ORDER BY monthly_spend;
--- solution
SELECT customer_id, name, monthly_spend
FROM customers
WHERE plan = 'Premium'
  AND region = 'North'
  AND monthly_spend > 100
ORDER BY monthly_spend DESC;
--- hints
- Combine conditions with `AND`.
- `ORDER BY column DESC` sorts from high to low.
