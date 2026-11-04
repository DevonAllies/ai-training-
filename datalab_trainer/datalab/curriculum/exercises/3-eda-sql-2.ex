id: eda-sql-2
stage: eda
lang: sql
title: Monthly revenue trend for 2024
ordered: true
--- task
Revenue for an order line is `quantity * unit_price * (1 - discount)`.

From the **`orders`** view return, for each month of **2024**:

* `month` – the first day of the month (`date_trunc('month', order_date)`)
* `orders` – number of orders
* `revenue` – total revenue rounded to 2 decimals

in month order (12 rows).
--- starter
SELECT order_date, quantity * unit_price * (1 - discount) AS revenue
FROM orders
LIMIT 10;
--- solution
SELECT date_trunc('month', order_date)                         AS month,
       count(*)                                                AS orders,
       round(sum(quantity * unit_price * (1 - discount)), 2)   AS revenue
FROM orders
WHERE order_date >= DATE '2024-01-01' AND order_date < DATE '2025-01-01'
GROUP BY month
ORDER BY month;
--- hints
- Filter with `WHERE year(order_date) = 2024` or a date range.
- `GROUP BY month` can refer to the alias in DuckDB.
