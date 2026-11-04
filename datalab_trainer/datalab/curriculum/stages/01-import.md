id: import
title: Import
summary: Get data out of files and databases and into a table you can trust.
--- lesson
# Module 1 · Import

Every analysis starts by getting data into memory **without silently changing it**.
In this course you work for *Ridgeway Retail*, a subscription retailer. Its data lives in
several places, just like at a real company:

| File | What it is | Format |
|---|---|---|
| `data/customers_raw.csv` | CRM export, one row per customer (messy!) | CSV |
| `data/orders.csv` | every order 2021–2024 | CSV |
| `data/products.json` | product categories and margins | JSON |
| `data/ridgeway.db` | stores and revenue targets | SQLite database |
| `data/customers.csv` | the *cleaned* customer table (answer key for Module 2) | CSV |
| `data/rentals_raw.csv` | bike rentals, used in the capstone project | CSV |

All paths are relative to your **workspace** folder (shown on the Setup page), so the same
code works on Windows and Ubuntu. Use forward slashes `data/orders.csv` — they work on both.

## Reading a CSV

```sql
-- DuckDB reads files directly; read_csv_auto guesses types and the delimiter
SELECT * FROM read_csv_auto('data/orders.csv') LIMIT 5;
```
```python
import pandas as pd
orders = pd.read_csv("data/orders.csv", parse_dates=["order_date"])
orders.head()
```
```r
orders <- read.csv("data/orders.csv", stringsAsFactors = FALSE)
orders$order_date <- as.Date(orders$order_date)
head(orders)
```

## The first five things to check after any import

1. **Shape** — rows × columns. Does it match what the source system says?
2. **Column types** — numbers stored as text (`"$52,000"`) are a cleaning job, not an import job, but you must *notice* them now.
3. **Missing values** — empty strings, `NA`, `NULL`, `-1`, `999`… each source has its own habit.
4. **Keys** — is the ID column unique? (`customers_raw.csv` is not!)
5. **Encoding & dates** — accents and `05/01/2023` (is that 5 Jan or 1 May?).

```sql
DESCRIBE SELECT * FROM read_csv_auto('data/customers_raw.csv');
SUMMARIZE SELECT * FROM read_csv_auto('data/customers_raw.csv');
```
```python
raw = pd.read_csv("data/customers_raw.csv")
print(raw.shape)
raw.info()                    # types and non-null counts
raw["customer_id"].is_unique  # False -> duplicates to deal with
```
```r
raw <- read.csv("data/customers_raw.csv", stringsAsFactors = FALSE)
dim(raw)
str(raw)
anyDuplicated(raw$customer_id) > 0
```

## Read raw data as text first

When a file is messy, read every column as **text** so nothing is lost, then convert on
purpose during cleaning. Automatic type guessing can turn `"0012"` into `12`, or a column of
mostly numbers with one `"n/a"` into text without telling you.

```sql
SELECT * FROM read_csv('data/customers_raw.csv', header = true, all_varchar = true);
```
```python
raw = pd.read_csv("data/customers_raw.csv", dtype=str, keep_default_na=False)
```
```r
raw <- read.csv("data/customers_raw.csv", colClasses = "character", na.strings = character(0))
```

## JSON and databases

```sql
SELECT * FROM read_json_auto('data/products.json');
```
```python
import json, sqlite3
products = pd.read_json("data/products.json")
con = sqlite3.connect("data/ridgeway.db")
stores = pd.read_sql("SELECT * FROM stores", con)
con.close()
```
```r
# install.packages(c("jsonlite", "DBI", "RSQLite"))
products <- jsonlite::fromJSON("data/products.json")
con <- DBI::dbConnect(RSQLite::SQLite(), "data/ridgeway.db")
stores <- DBI::dbGetQuery(con, "SELECT * FROM stores")
DBI::dbDisconnect(con)
```

> **Tip:** In the SQL exercises every CSV in `data/` is also available as a ready-made
> view named after the file (`customers`, `customers_raw`, `orders`, `rentals_raw`) and
> `products` for the JSON file. In this stage practise `read_csv_auto` so you know how it works.

## Other formats you will meet

* **Excel**: `pd.read_excel("file.xlsx", sheet_name="Sheet1")` (needs `openpyxl`); R `readxl::read_excel()`; DuckDB `st_read` or the `excel` extension.
* **Parquet** (fast, typed, compressed): `pd.read_parquet()`, `arrow::read_parquet()`, `SELECT * FROM 'file.parquet'`.
* **APIs**: `requests.get(url).json()` / `httr2` — then the result is JSON again.
--- quiz
Q: You import a CSV and the `income` column has type text/object. What is the most likely reason?
- The file is corrupted
* Some values contain non-numeric characters such as "$" or ","
- pandas cannot read numbers from CSV files
- The column has too many rows
E: One bad value is enough to turn a whole column into text. Find and fix it in the cleaning stage.
Q: Why read a messy file with every column as text first?
- It is faster
- Text uses less memory
* Nothing is silently converted or lost, so you decide each conversion yourself
- SQL cannot read numbers
E: Automatic type guessing can drop leading zeros, mis-read dates or hide bad values.
Q: Which check tells you whether customer_id can be used as a key?
- Counting the columns
* Checking whether customer_id is unique
- Checking the file size
- Sorting by customer_id
E: A key must identify exactly one row. Duplicates mean the same customer appears more than once.
Q: What does `05/01/2023` mean?
- Always 5 January 2023
- Always 1 May 2023
* It depends on the source's date convention; you must find out and parse it explicitly
E: Day-first (most of the world) and month-first (US) formats look identical for days ≤ 12.
