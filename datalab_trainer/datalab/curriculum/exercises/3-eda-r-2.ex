id: eda-r-2
stage: eda
lang: r
title: Base-R charts and correlation matrix
--- task
Make **at least two charts** with base R graphics (or ggplot2 if installed):

1. `hist()` of `monthly_spend`,
2. `boxplot(monthly_spend ~ plan, data = df)` or `barplot()` of churn rate by plan,

with titles (`main =`) and axis labels (`xlab =`, `ylab =`). Then create

* **`cm`** – the correlation matrix (`cor()`) of
  `age, income, tenure_months, support_calls, monthly_spend, churned`.
--- starter
df <- read.csv("data/customers.csv")

# TODO charts

cm <- NA
--- solution
df <- read.csv("data/customers.csv")
df$plan <- factor(df$plan, levels = c("Basic", "Standard", "Premium"))

hist(df$monthly_spend, breaks = 30, col = "steelblue", border = "white",
     main = "Half of customers spend 58-86 per month", xlab = "Monthly spend", ylab = "Customers")

boxplot(monthly_spend ~ plan, data = df, col = "grey90",
        main = "Premium customers spend the most", xlab = "Plan", ylab = "Monthly spend")

cols <- c("age", "income", "tenure_months", "support_calls", "monthly_spend", "churned")
cm <- cor(df[, cols])
print(round(cm, 2))
--- check
expect(length(list.files(.dl$out, pattern = "^fig_")) >= 2 ||
       (dev.cur() > 1 && length(list.files(.dl$out, pattern = "^fig_")) >= 1),
       "Make at least two charts.")
ref <- read.csv("data/customers.csv")
r <- cor(ref[, c("age", "income", "tenure_months", "support_calls", "monthly_spend", "churned")])
expect(is.matrix(cm) && all(dim(cm) == c(6, 6)), "cm should be a 6 x 6 correlation matrix.")
expect(abs(cm["income", "monthly_spend"] - r["income", "monthly_spend"]) < 1e-9, "cm values don't match cor() of the listed columns.")
--- hints
- `hist(x, main = "...", xlab = "...")`
- `boxplot(y ~ group, data = df)`
- `cor(df[, cols])`
