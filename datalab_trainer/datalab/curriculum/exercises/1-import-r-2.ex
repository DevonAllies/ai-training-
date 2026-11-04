id: import-r-2
stage: import
lang: r
title: Import orders and convert dates
--- task
Read **`data/orders.csv`** into **`orders`** and convert `order_date` to R's `Date` class.

Then create:

* `date_range` – a length-2 Date vector: first and last order date (`range()`)
* `n_categories` – the number of distinct product categories
* `orders_per_year` – a table of the number of orders per year (`table(format(..., "%Y"))`)
--- starter
orders <- read.csv("data/orders.csv", stringsAsFactors = FALSE)
# TODO convert order_date to Date

date_range <- NA
n_categories <- NA
orders_per_year <- NA
--- solution
orders <- read.csv("data/orders.csv", stringsAsFactors = FALSE)
orders$order_date <- as.Date(orders$order_date)

date_range <- range(orders$order_date)
n_categories <- length(unique(orders$category))
orders_per_year <- table(format(orders$order_date, "%Y"))
print(date_range); print(n_categories); print(orders_per_year)
--- check
expect(nrow(orders) == 4000, "orders should have 4000 rows.")
expect(inherits(orders$order_date, "Date"), "orders$order_date should have class Date: use as.Date().")
expect(inherits(date_range, "Date") && length(date_range) == 2, "date_range should be range(orders$order_date).")
expect(date_range[2] <= as.Date("2024-12-31"), "The last order should be in 2024.")
expect(n_categories == 6, "There are 6 categories: length(unique(orders$category)).")
expect(sum(orders_per_year) == 4000 && length(orders_per_year) == 4, "orders_per_year should count orders in each of 4 years.")
--- hints
- ISO dates (2024-01-31) convert directly with `as.Date(x)`.
- `format(date, "%Y")` gives the year as text.
