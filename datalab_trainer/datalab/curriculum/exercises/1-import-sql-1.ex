id: import-sql-1
stage: import
lang: sql
title: Read a CSV and count rows and customers
--- task
Use DuckDB's `read_csv_auto` to read **`data/customers_raw.csv`** and return **one row** with:

| column | meaning |
|---|---|
| `n_rows` | number of rows in the file |
| `n_customers` | number of *distinct* `customer_id` values |

If the two numbers differ, the file has duplicates. Note them down, because you'll fix them in Module 2 (Clean).
--- starter
-- Count rows and distinct customers in the raw CRM export
SELECT
    count(*) AS n_rows
    -- add n_customers here
FROM read_csv_auto('data/customers_raw.csv');
--- solution
SELECT
    count(*)                    AS n_rows,
    count(DISTINCT customer_id) AS n_customers
FROM read_csv_auto('data/customers_raw.csv');
--- hints
- `count(DISTINCT column)` counts unique values.
- Separate the two expressions in the SELECT list with a comma.
