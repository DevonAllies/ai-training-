id: import-sql-3
stage: import
lang: sql
title: Inspect column types before you trust them
level: 2
--- task
`DESCRIBE` shows the type DuckDB guessed for each column. Run

```sql
DESCRIBE SELECT * FROM read_csv_auto('data/customers_raw.csv');
```

and look at it. Then write a query that returns **one row per column whose guessed type is text (`VARCHAR`)**
with the columns `column_name` and `column_type`.

Ask yourself: which of these columns *should* be numbers or dates? Those are your cleaning jobs.
--- starter
DESCRIBE SELECT * FROM read_csv_auto('data/customers_raw.csv');
--- solution
SELECT column_name, column_type
FROM (DESCRIBE SELECT * FROM read_csv_auto('data/customers_raw.csv'))
WHERE column_type = 'VARCHAR';
--- hints
- You can use the output of DESCRIBE as a sub-query: `SELECT ... FROM (DESCRIBE SELECT ...)`.
- Filter with `WHERE column_type = 'VARCHAR'`.
