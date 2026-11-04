id: import-sql-2
stage: import
lang: sql
title: Read JSON and sort the result
ordered: true
--- task
`data/products.json` lists Ridgeway's product categories. Read it with **`read_json_auto`** and return:

* `category`
* `department`
* `margin_pct` – the `margin` column as a percentage, rounded to 1 decimal (0.18 → 18.0)

sorted from the **highest margin to the lowest**. Row order is checked in this task.
--- starter
SELECT *
FROM read_json_auto('data/products.json');
--- solution
SELECT category,
       department,
       round(margin * 100, 1) AS margin_pct
FROM read_json_auto('data/products.json')
ORDER BY margin_pct DESC;
--- hints
- `round(x, 1)` rounds to one decimal place.
- `ORDER BY margin_pct DESC` sorts from high to low.
