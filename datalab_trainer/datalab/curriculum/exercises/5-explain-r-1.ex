id: explain-r-1
stage: explain
lang: r
title: SHAP by hand for lm() in R
--- task
Fit `fit <- lm(monthly_spend ~ income + age + tenure_months, data = df)` on all customers and
compute exact SHAP values by hand:

* **`phi`** – a 600 × 3 matrix: `(x − column mean) × coefficient` for each feature
  (columns named `income`, `age`, `tenure_months`)
* **`base`** – mean of the fitted values
* **`importance`** – named numeric vector of mean |φ|, sorted descending

Check additivity: `base + rowSums(phi)` should equal `fitted(fit)`.
--- starter
df <- read.csv("data/customers.csv")
fit <- lm(monthly_spend ~ income + age + tenure_months, data = df)
X <- as.matrix(df[, c("income", "age", "tenure_months")])

phi <- NA
base <- NA
importance <- NA
--- solution
df <- read.csv("data/customers.csv")
fit <- lm(monthly_spend ~ income + age + tenure_months, data = df)
X <- as.matrix(df[, c("income", "age", "tenure_months")])

b <- coef(fit)[colnames(X)]
phi <- sweep(sweep(X, 2, colMeans(X)), 2, b, `*`)
base <- mean(fitted(fit))
stopifnot(isTRUE(all.equal(unname(base + rowSums(phi)), unname(fitted(fit)))))

importance <- sort(colMeans(abs(phi)), decreasing = TRUE)
print(round(importance, 2))
barplot(rev(importance), horiz = TRUE, las = 1, main = "Income drives spend (mean |SHAP|)")
--- check
ref <- read.csv("data/customers.csv")
f <- lm(monthly_spend ~ income + age + tenure_months, data = ref)
expect(is.matrix(phi) && all(dim(phi) == c(600, 3)), "phi should be a 600 x 3 matrix.")
expect(isTRUE(all.equal(unname(as.numeric(base) + rowSums(phi)), unname(fitted(f)), tolerance = 1e-6)),
       "Additivity fails: base + rowSums(phi) should equal fitted(fit). Subtract the column means first.")
expect(is.numeric(importance) && names(importance)[1] == "income", "importance should be sorted descending with income first.")
CHECK_MESSAGE <- "Exact SHAP values: they add up to every fitted value."
--- hints
- `sweep(X, 2, colMeans(X))` subtracts each column's mean.
- `sweep(M, 2, b, `*`)` multiplies each column by its coefficient.
- `sort(colMeans(abs(phi)), decreasing = TRUE)`
