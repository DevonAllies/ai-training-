id: eda-r-1
stage: eda
lang: r
title: Summaries and group comparisons in R
--- task
Load **`data/customers.csv`** into `df`, then create:

* **`rates`** – churn rate by plan: a named numeric vector, e.g. via `tapply(df$churned, df$plan, mean)`, **sorted high to low**,
* **`spend_by_region`** – mean `monthly_spend` by region (named vector),
* **`calls_rates`** – churn rate per band of `support_calls` using
  `cut(df$support_calls, c(-1, 1, 3, 100), labels = c("0-1", "2-3", "4+"))`.

Also run `summary(df)` and look at the output.
--- starter
df <- read.csv("data/customers.csv")
summary(df)

rates <- NA
spend_by_region <- NA
calls_rates <- NA
--- solution
df <- read.csv("data/customers.csv")
summary(df)

rates <- sort(tapply(df$churned, df$plan, mean), decreasing = TRUE)
spend_by_region <- tapply(df$monthly_spend, df$region, mean)
band <- cut(df$support_calls, c(-1, 1, 3, 100), labels = c("0-1", "2-3", "4+"))
calls_rates <- tapply(df$churned, band, mean)
print(round(rates, 3)); print(round(spend_by_region, 2)); print(round(calls_rates, 3))
--- check
ref <- read.csv("data/customers.csv")
e <- sort(tapply(ref$churned, ref$plan, mean), decreasing = TRUE)
expect(is.numeric(rates) && identical(names(rates), names(e)), paste("rates should be named by plan and sorted high to low:", paste(names(e), collapse = ", ")))
expect(all(abs(as.numeric(rates) - as.numeric(e)) < 1e-9), "rates values are wrong: use tapply(df$churned, df$plan, mean).")
s <- tapply(ref$monthly_spend, ref$region, mean)
expect(all(abs(as.numeric(spend_by_region[names(s)]) - as.numeric(s)) < 1e-9), "spend_by_region should be mean monthly_spend per region.")
b <- cut(ref$support_calls, c(-1, 1, 3, 100), labels = c("0-1", "2-3", "4+"))
cr <- tapply(ref$churned, b, mean)
expect(length(calls_rates) == 3 && all(abs(as.numeric(calls_rates[names(cr)]) - as.numeric(cr)) < 1e-9), "calls_rates should be churn rate per band.")
--- hints
- `tapply(values, groups, FUN)` applies FUN to each group.
- `sort(x, decreasing = TRUE)` keeps the names.
