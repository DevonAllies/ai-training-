id: model-sql-2
stage: model
lang: sql
title: Build a model-ready feature table
--- task
Models need **one row per customer** with numeric features. Join `customers` to an
aggregate of `orders` and return:

| column | definition |
|---|---|
| `customer_id` | |
| `n_orders` | number of orders (0 if none) |
| `revenue` | total `quantity * unit_price * (1 - discount)`, rounded to 2 dp (0 if none) |
| `days_since_last` | days from the last order to `DATE '2024-12-31'` (NULL if no orders) |
| `is_basic`, `is_premium` | 1/0 one-hot flags for the plan (Standard is the reference level) |
| `tenure_months`, `support_calls`, `churned` | copied from customers |

One row for **every** customer (600 rows), so use a `LEFT JOIN`.
--- starter
WITH o AS (
    SELECT customer_id, count(*) AS n_orders
    FROM orders
    GROUP BY customer_id
)
SELECT c.customer_id, o.n_orders
FROM customers c
JOIN o USING (customer_id);
--- solution
WITH o AS (
    SELECT customer_id,
           count(*)                                              AS n_orders,
           sum(quantity * unit_price * (1 - discount))           AS revenue,
           max(order_date)                                       AS last_order
    FROM orders
    GROUP BY customer_id
)
SELECT c.customer_id,
       coalesce(o.n_orders, 0)                             AS n_orders,
       round(coalesce(o.revenue, 0), 2)                    AS revenue,
       date_diff('day', o.last_order, DATE '2024-12-31')   AS days_since_last,
       CASE WHEN c.plan = 'Basic'   THEN 1 ELSE 0 END      AS is_basic,
       CASE WHEN c.plan = 'Premium' THEN 1 ELSE 0 END      AS is_premium,
       c.tenure_months,
       c.support_calls,
       c.churned
FROM customers c
LEFT JOIN o USING (customer_id);
--- hints
- Aggregate orders in a CTE first, then `LEFT JOIN` so customers without orders stay.
- `coalesce(x, 0)` replaces NULL with 0.
- `date_diff('day', start, end)` counts days.
