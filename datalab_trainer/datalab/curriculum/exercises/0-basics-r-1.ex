id: basics-r-1
stage: basics
lang: r
title: R essentials - vectors, functions, indexing
--- task
Using base R:

1. Compute **`total`** (`sum()`) and **`avg`** (`mean()`) of the vector `spends`.
2. Write a function **`annual <- function(monthly) ...`** that returns monthly × 12.
3. **`big`** – the spends above 60 (logical indexing: `spends[spends > 60]`).
4. **`counts`** – how often each plan occurs: `table(plans)`.
5. **`second`** – the second element of `spends` (remember: R counts from 1).
--- starter
spends <- c(52.1, 80.0, 61.5, 45.0, 99.9, 70.25)
plans <- c("Basic", "Premium", "Basic", "Standard", "Basic", "Premium")

total <- NA
avg <- NA
annual <- function(monthly) NA
big <- NA
counts <- NA
second <- NA
--- solution
spends <- c(52.1, 80.0, 61.5, 45.0, 99.9, 70.25)
plans <- c("Basic", "Premium", "Basic", "Standard", "Basic", "Premium")

total <- sum(spends)
avg <- mean(spends)
annual <- function(monthly) monthly * 12
big <- spends[spends > 60]
counts <- table(plans)
second <- spends[2]
print(total); print(avg); print(annual(19.99)); print(big); print(counts); print(second)
--- check
expect(isTRUE(all.equal(total, 408.75)), "total should be sum(spends) = 408.75.")
expect(isTRUE(all.equal(avg, 408.75 / 6)), "avg should be mean(spends).")
expect(is.function(annual) && isTRUE(all.equal(annual(10), 120)), "annual(10) should return 120.")
expect(isTRUE(all.equal(big, c(80.0, 61.5, 99.9, 70.25))), "big should be spends[spends > 60].")
expect(as.integer(counts[["Basic"]]) == 3 && as.integer(counts[["Premium"]]) == 2, "counts should be table(plans).")
expect(identical(second, 80), "second should be spends[2] (R counts from 1).")
--- hints
- `sum()`, `mean()` work on a whole vector.
- `spends > 60` gives TRUE/FALSE for each element; use it inside `[ ]`.
