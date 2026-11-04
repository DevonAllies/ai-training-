id: basics
title: Foundations
summary: First steps in SQL, Python and R: tables, values, variables, functions and filtering.
--- lesson
# Module 0 · Foundations

New to SQL, Python or R? Start here. If you can already write a `SELECT … WHERE … GROUP BY`
query, a Python function and an R data frame filter, skip to **Module 1**.

## The three tools, and what each is good at

| | SQL | Python | R |
|---|---|---|---|
| What it is | a language for asking questions of **tables** in a database | a general-purpose programming language | a language built for **statistics** |
| Best at | filtering, joining and summarising large tables | automation, machine learning, anything else | statistical modelling, quick analysis, charts |
| Main data structure | table | pandas `DataFrame` | `data.frame` |
| In this course | DuckDB | pandas, scikit-learn, matplotlib | base R |

Most data teams use **SQL to get the data** and **Python or R to analyse it**. You'll practise all three
on the same data, so you can see how each one solves the same problem.

## Running code in DataLab

* Type in the editor, press **Ctrl+Enter** to run and **Ctrl+Shift+Enter** to check.
* Python and R `print()` output appears below the editor. A SQL query shows its result table.
* `#` starts a comment in Python and R; `--` starts a comment in SQL.

## SQL: asking a table questions

A query always has the same shape, written in this order:

```sql
SELECT   column1, column2          -- which columns
FROM     customers                 -- which table
WHERE    plan = 'Premium'          -- which rows (filter before grouping)
ORDER BY monthly_spend DESC        -- sort
LIMIT    10;                       -- how many rows
```

Summaries use **aggregate functions** with `GROUP BY`. `HAVING` filters *after* grouping:

```sql
SELECT region, count(*) AS customers, avg(age) AS avg_age
FROM customers
GROUP BY region
HAVING count(*) > 140;
```

Text goes in **single quotes** (`'North'`). Combine conditions with `AND` / `OR`. Test for a missing value with
`IS NULL` (never `= NULL`).

## Python: values, lists, dictionaries, functions

```python
price = 19.99                     # a number (float)
plan = "Basic"                    # text (str)
spends = [52.1, 80.0, 61.5]       # a list
fees = {"Basic": 19.99, "Premium": 69.99}   # a dictionary: key -> value

total = 0
for s in spends:                  # a loop: the indented block runs once per item
    total = total + s
mean = total / len(spends)

def annual(monthly):              # a function: reusable code with an input
    return monthly * 12

print(f"Mean {mean:.2f}, Premium per year {annual(fees['Premium']):.2f}")
```

Indentation is part of the language: the lines that belong to a `for` or `def` are indented by 4 spaces.

## Python: your first DataFrame

```python
import pandas as pd
df = pd.read_csv("data/customers.csv")      # a table
df.head()                                    # first rows
df["income"]                                 # one column (a Series)
df[["name", "plan"]]                         # several columns
df[df["plan"] == "Premium"]                  # filter rows
df[(df["plan"] == "Premium") & (df["region"] == "North")]   # & = and, | = or (with brackets!)
df.sort_values("monthly_spend", ascending=False)
df["annual_spend"] = df["monthly_spend"] * 12               # new column
```

## R: vectors, functions and data frames

In R almost everything is a **vector**, and operations work on the whole vector at once:

```r
spends <- c(52.1, 80.0, 61.5)     # <- assigns a value
mean(spends)
spends * 12                        # every element times 12
spends[spends > 60]                # filter with a condition
annual <- function(monthly) monthly * 12

df <- read.csv("data/customers.csv")
head(df)
df$income                                   # one column
df[df$plan == "Premium" & df$region == "North", c("name", "monthly_spend")]
df[order(-df$monthly_spend), ]              # sort descending
df$annual_spend <- df$monthly_spend * 12    # new column
```

Indexing is `df[rows, columns]`. Leave one side empty to mean "all". R counts from **1**, Python from **0**.

## Getting help

* SQL: <https://duckdb.org/docs/sql/introduction>
* Python: `help(pd.read_csv)`, or <https://pandas.pydata.org/docs/user_guide/10min.html>
* R: `?read.csv` or `help(mean)`
* Read error messages from the **bottom up**: the last line says what went wrong, and the lines above say where.
--- quiz
Q: In SQL, which clause filters rows *after* grouping?
- WHERE
* HAVING
- ORDER BY
- LIMIT
E: WHERE filters individual rows before grouping; HAVING filters groups after aggregation.
Q: In pandas, how do you keep Premium customers in the North region?
- df[df.plan == "Premium" and df.region == "North"]
* df[(df.plan == "Premium") & (df.region == "North")]
- df.filter("Premium", "North")
E: Use & between conditions in brackets. Python's `and` doesn't work element by element.
Q: What does `x[1]` return in R for `x <- c(10, 20, 30)`?
* 10
- 20
- An error
E: R counts from 1. In Python the same index would give 20.
Q: How do you test for a missing value in SQL?
- income = NULL
* income IS NULL
- income == NA
E: NULL means unknown, and comparing anything with `=` to NULL is never true.
