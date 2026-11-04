id: clean-sql-1
stage: clean
lang: sql
title: Remove duplicates and standardise region labels
--- task
The `region` column in the raw export is spelled many ways: `North`, `north `, `N`, `N.`, `NORTH` …

Starting from `read_csv('data/customers_raw.csv', header = true, all_varchar = true)`:

1. Keep **one row per `customer_id`** (the file has 18 duplicated rows).
2. Turn region into exactly one of `North`, `South`, `East`, `West`.
3. Return `region` and `n` (number of customers), one row per region.

First run `SELECT region, count(*) FROM customers_raw GROUP BY ALL` to see the mess.
--- starter
WITH dedup AS (
    SELECT *
    FROM read_csv('data/customers_raw.csv', header = true, all_varchar = true)
    -- TODO keep one row per customer_id (QUALIFY row_number() ...)
)
SELECT region, count(*) AS n
FROM dedup
GROUP BY region;
--- solution
WITH dedup AS (
    SELECT *
    FROM read_csv('data/customers_raw.csv', header = true, all_varchar = true)
    QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY customer_id) = 1
)
SELECT CASE upper(left(trim(region), 1))
            WHEN 'N' THEN 'North' WHEN 'S' THEN 'South'
            WHEN 'E' THEN 'East'  WHEN 'W' THEN 'West'
       END      AS region,
       count(*) AS n
FROM dedup
GROUP BY 1;
--- hints
- `QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY customer_id) = 1` keeps the first row of each customer.
- `upper(left(trim(region), 1))` reduces every spelling to its first letter: N, S, E or W.
- Use `CASE ... WHEN 'N' THEN 'North' ... END` to map letters to names.
