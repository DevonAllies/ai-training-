id: clean-sql-2
stage: clean
lang: sql
title: Profile numbers stored as text
--- task
`income` holds values like `"$55,600"`, `"55600"` and empty strings, and `age` contains
impossible values (`-1`, `0`, `150`, `999`) as well as blanks.

Using the **de-duplicated** raw data (one row per `customer_id`), return one row with:

| column | definition |
|---|---|
| `missing_income` | rows where income can't be converted to a number (blank) |
| `median_income` | median of the converted income values |
| `missing_age` | rows where age is blank |
| `bad_age` | rows where age is a number but outside 18–100 |

`TRY_CAST(x AS DOUBLE)` returns NULL instead of an error when `x` isn't a number.
--- starter
WITH dedup AS (
    SELECT *
    FROM read_csv('data/customers_raw.csv', header = true, all_varchar = true)
    QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY customer_id) = 1
),
parsed AS (
    SELECT TRY_CAST(income AS DOUBLE) AS income_num,   -- TODO strip '$' and ',' first
           TRY_CAST(age AS DOUBLE)    AS age_num
    FROM dedup
)
SELECT count(*) FILTER (WHERE income_num IS NULL) AS missing_income
FROM parsed;
--- solution
WITH dedup AS (
    SELECT *
    FROM read_csv('data/customers_raw.csv', header = true, all_varchar = true)
    QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY customer_id) = 1
),
parsed AS (
    SELECT TRY_CAST(replace(replace(income, '$', ''), ',', '') AS DOUBLE) AS income_num,
           TRY_CAST(age AS DOUBLE) AS age_num
    FROM dedup
)
SELECT count(*) FILTER (WHERE income_num IS NULL)                         AS missing_income,
       median(income_num)                                                  AS median_income,
       count(*) FILTER (WHERE age_num IS NULL)                             AS missing_age,
       count(*) FILTER (WHERE age_num IS NOT NULL AND age_num NOT BETWEEN 18 AND 100) AS bad_age
FROM parsed;
--- hints
- `replace(replace(income, '$', ''), ',', '')` removes both characters.
- `count(*) FILTER (WHERE condition)` counts rows meeting a condition.
- `median(x)` ignores NULLs.
