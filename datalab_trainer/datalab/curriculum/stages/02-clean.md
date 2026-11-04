id: clean
title: Clean
summary: Fix duplicates, inconsistent labels, bad numbers, impossible values and mixed dates.
--- lesson
# Stage 2 · Clean

Cleaning turns *what the source system gave you* into *what the data actually means*.
It's usually the biggest part of a real project. Do it **in code**, never by hand in a
spreadsheet, so it can be repeated and reviewed.

`customers_raw.csv` contains every problem below. The cleaned result is in
`data/customers.csv`, so you can compare your work against it.

| Problem | Example in the data | Fix |
|---|---|---|
| Duplicate rows | 18 customers appear twice | keep the first row per `customer_id` |
| Stray spaces / case | `"  sipho mahlangu "` | trim, then Title Case |
| Inconsistent labels | `North`, `north `, `N`, `N.` | map to one spelling |
| Numbers as text | `"$55,600"` | remove `$` and `,`, convert |
| Impossible values | age `-1`, `0`, `999` | set to missing |
| Missing values | empty age / income | impute (median) **and say so in the report** |
| Mixed date formats | `2021-08-24` and `26/03/2024` | parse each format explicitly |
| Mixed booleans | `Yes`, `Y`, `1`, `TRUE`, `no` | map to 1 / 0 |
| Invalid emails | no `@` | set to missing |

## The cleaning workflow

1. **Profile** – count distinct values of every text column, look at min/max of numbers.
2. **Write rules** – one line of code per rule, with a comment saying *why*.
3. **Validate** – assert the rules hold afterwards (unique keys, allowed values, ranges).
4. **Record** – keep a short log: how many rows were removed, imputed or changed.

## Duplicates

```sql
SELECT * FROM customers_raw
QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY customer_id) = 1;
```
```python
df = raw.drop_duplicates(subset="customer_id", keep="first")
```
```r
df <- raw[!duplicated(raw$customer_id), ]
```

## Text: trim, case and mapping labels

```sql
SELECT CASE upper(left(trim(region), 1))
         WHEN 'N' THEN 'North' WHEN 'S' THEN 'South'
         WHEN 'E' THEN 'East'  WHEN 'W' THEN 'West' END AS region
FROM customers_raw;
```
```python
df["name"] = df["name"].str.strip().str.title()
region_map = {"N": "North", "S": "South", "E": "East", "W": "West"}
df["region"] = df["region"].str.strip().str.upper().str[0].map(region_map)
```
```r
df$name <- tools::toTitleCase(tolower(trimws(df$name)))
region_map <- c(N = "North", S = "South", E = "East", W = "West")
df$region <- unname(region_map[toupper(substr(trimws(df$region), 1, 1))])
```

## Numbers stored as text, impossible values and imputation

```sql
SELECT TRY_CAST(replace(replace(income, '$', ''), ',', '') AS DOUBLE) AS income,
       CASE WHEN TRY_CAST(age AS INTEGER) BETWEEN 18 AND 100 THEN TRY_CAST(age AS INTEGER) END AS age
FROM read_csv('data/customers_raw.csv', all_varchar = true);
```
```python
df["income"] = pd.to_numeric(df["income"].str.replace(r"[$,]", "", regex=True), errors="coerce")
age = pd.to_numeric(df["age"], errors="coerce")
df["age"] = age.where(age.between(18, 100))          # impossible -> NaN
df["age"] = df["age"].fillna(df["age"].median())     # impute
```
```r
df$income <- as.numeric(gsub("[$,]", "", df$income))   # "" becomes NA
age <- suppressWarnings(as.numeric(df$age))
age[!is.na(age) & (age < 18 | age > 100)] <- NA
df$age <- ifelse(is.na(age), median(age, na.rm = TRUE), age)
```

**Median, not mean**, for skewed numbers like income: one millionaire moves the mean a lot
and the median hardly at all. Imputation hides uncertainty, so always report how many
values you filled in. For modelling you can also add a flag column `income_was_missing`.

## Dates in more than one format

```sql
SELECT coalesce(try_strptime(signup_date, '%Y-%m-%d'),
                try_strptime(signup_date, '%d/%m/%Y'))::DATE AS signup_date
FROM read_csv('data/customers_raw.csv', all_varchar = true);
```
```python
iso = pd.to_datetime(df["signup_date"], format="%Y-%m-%d", errors="coerce")
dmy = pd.to_datetime(df["signup_date"], format="%d/%m/%Y", errors="coerce")
df["signup_date"] = iso.fillna(dmy)
```
```r
d <- as.Date(df$signup_date, format = "%Y-%m-%d")
d[is.na(d)] <- as.Date(df$signup_date[is.na(d)], format = "%d/%m/%Y")
df$signup_date <- d
```

## Validate with assertions

```python
assert df["customer_id"].is_unique
assert df["region"].isin(["North", "South", "East", "West"]).all()
assert df["age"].between(18, 100).all()
```
```r
stopifnot(!anyDuplicated(df$customer_id),
          all(df$region %in% c("North", "South", "East", "West")))
```

> **Tidyverse version (R):** `dplyr::distinct()`, `mutate()`, `stringr::str_trim()`,
> `readr::parse_number("$55,600")` and `lubridate::parse_date_time(x, c("ymd", "dmy"))`
> do the same jobs with less typing. Install with `install.packages("tidyverse")`.
--- quiz
Q: Income is right-skewed. Which value is the better default for filling missing incomes?
- The mean
* The median
- Zero
- The maximum
E: The median isn't pulled up by a few very high incomes. Filling with zero would invent poor customers.
Q: An age of 999 appears. What should you do first?
- Delete the whole customer
* Treat it as missing (it's an error code or typo), then decide how to handle missing ages
- Keep it, it's real data
- Replace it with 99
E: Impossible values are usually codes or typos. Turn them into missing values so they don't distort averages.
Q: Why is it a bad idea to clean data by hand in Excel?
- Excel can't open CSV files
* The steps can't be repeated, reviewed or re-run when new data arrives
- It is always slower
E: Code is a record of every decision. Next month's export can be cleaned by running the same script.
Q: After cleaning, what is the purpose of assertions such as `assert df.customer_id.is_unique`?
- They make the code faster
* They prove the cleaning rules hold and stop the pipeline if new data breaks them
- They are required by pandas
E: Assertions turn assumptions into checks. If a new export has a new problem, you find out immediately.
