id: import-r-1
stage: import
lang: r
title: Read a messy CSV safely in base R
--- task
Read **`data/customers_raw.csv`** into a data frame **`raw`** with **every column as character**
(`colClasses = "character"`), so nothing is converted automatically.

Then create:

* `n_rows` – number of rows
* `n_dupes` – number of rows whose `customer_id` already appeared earlier

Use `str(raw)` to look at the result.
--- starter
raw <- read.csv("data/customers_raw.csv")   # TODO: keep every column as character

n_rows <- NA    # TODO
n_dupes <- NA   # TODO

str(raw)
--- solution
raw <- read.csv("data/customers_raw.csv", colClasses = "character")

n_rows <- nrow(raw)
n_dupes <- sum(duplicated(raw$customer_id))

str(raw)
cat(n_rows, "rows,", n_dupes, "duplicated customer_id values\n")
--- check
expect(is.data.frame(raw), "`raw` should be a data frame.")
expect(nrow(raw) == 618 && ncol(raw) == 13, "`raw` should have 618 rows and 13 columns.")
expect(all(vapply(raw, is.character, logical(1))), "Every column should be character: colClasses = \"character\".")
expect(identical(as.integer(n_rows), 618L), "n_rows should be nrow(raw).")
expect(identical(as.integer(n_dupes), 18L), "n_dupes should be 18. Try sum(duplicated(raw$customer_id)).")
CHECK_MESSAGE <- "Correct: 618 rows and 18 duplicates, all kept as text."
--- hints
- `read.csv(path, colClasses = "character")`
- `duplicated(x)` is TRUE for the second and later copies; `sum()` counts TRUEs.
