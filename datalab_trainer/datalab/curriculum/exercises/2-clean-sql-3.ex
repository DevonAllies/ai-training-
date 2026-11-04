id: clean-sql-3
stage: clean
lang: sql
title: The full cleaning pipeline in one query
level: 2
--- task
Reproduce the answer-key table `customers` (columns below) from the raw file **in a single SQL query**.

Return `customer_id, region, age, income, plan, signup_date, churned` with these rules:

* one row per `customer_id`
* `region` → North / South / East / West
* `age` → integer; values outside 18–100 or blank become the **median of the valid ages**, rounded **down** (`floor`)
* `income` → number without `$` and `,`; blanks become the **median income**
* `plan` → `Basic` / `Standard` / `Premium` (trimmed, Title case)
* `signup_date` → a `DATE`; the file mixes `YYYY-MM-DD` and `DD/MM/YYYY`
* `churned` → 1 for yes / y / 1 / true (any case), else 0

Compare with `SELECT * FROM customers` when you get stuck.
--- starter
WITH dedup AS (
    SELECT *
    FROM read_csv('data/customers_raw.csv', header = true, all_varchar = true)
    QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY customer_id) = 1
)
SELECT customer_id, region, age, income, plan, signup_date, churned
FROM dedup;
--- solution
WITH dedup AS (
    SELECT *
    FROM read_csv('data/customers_raw.csv', header = true, all_varchar = true)
    QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY customer_id) = 1
),
parsed AS (
    SELECT customer_id,
           CASE upper(left(trim(region), 1))
                WHEN 'N' THEN 'North' WHEN 'S' THEN 'South'
                WHEN 'E' THEN 'East'  WHEN 'W' THEN 'West' END                     AS region,
           CASE WHEN TRY_CAST(age AS DOUBLE) BETWEEN 18 AND 100
                THEN TRY_CAST(age AS DOUBLE) END                                     AS age,
           TRY_CAST(replace(replace(income, '$', ''), ',', '') AS DOUBLE)           AS income,
           upper(left(trim(plan), 1)) || lower(substr(trim(plan), 2))               AS plan,
           coalesce(try_strptime(signup_date, '%Y-%m-%d'),
                    try_strptime(signup_date, '%d/%m/%Y'))::DATE                    AS signup_date,
           CASE WHEN lower(trim(churned)) IN ('yes', 'y', '1', 'true') THEN 1 ELSE 0 END AS churned
    FROM dedup
)
SELECT customer_id,
       region,
       CAST(floor(coalesce(age, median(age) OVER ())) AS INTEGER) AS age,
       coalesce(income, median(income) OVER ())                   AS income,
       plan,
       signup_date,
       churned
FROM parsed;
--- hints
- Do the parsing in one CTE and the imputation in the next: `coalesce(age, median(age) OVER ())`.
- `median(x) OVER ()` is a window function: the median of the whole column on every row.
- `coalesce(try_strptime(s, '%Y-%m-%d'), try_strptime(s, '%d/%m/%Y'))::DATE`
- Title case: `upper(left(x, 1)) || lower(substr(x, 2))`
