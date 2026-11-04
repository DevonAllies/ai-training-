id: model-r-1
stage: model
lang: r
title: Linear regression with lm()
--- task
Predict **`monthly_spend`** from `income + age + plan`.

1. `set.seed(42)` and put a random 75% of rows in `train`, the rest in `test`.
2. Fit **`fit <- lm(monthly_spend ~ income + age + plan, data = train)`** and look at `summary(fit)`.
3. Compute **`rmse`** on the test set and **`r2_test`**: `1 - SSE / SST` on the test set (SST around the *training* mean).

Read the summary: what does the `planPremium` coefficient mean in plain words?
--- starter
df <- read.csv("data/customers.csv", stringsAsFactors = TRUE)
set.seed(42)

fit <- NA
rmse <- NA
r2_test <- NA
--- solution
df <- read.csv("data/customers.csv", stringsAsFactors = TRUE)
set.seed(42)
idx <- sample(nrow(df), round(0.75 * nrow(df)))
train <- df[idx, ]
test <- df[-idx, ]

fit <- lm(monthly_spend ~ income + age + plan, data = train)
print(summary(fit))

pred <- predict(fit, newdata = test)
rmse <- sqrt(mean((test$monthly_spend - pred)^2))
r2_test <- 1 - sum((test$monthly_spend - pred)^2) / sum((test$monthly_spend - mean(train$monthly_spend))^2)
cat("Test RMSE:", round(rmse, 2), " Test R2:", round(r2_test, 3), "\n")
# planPremium: Premium customers spend about 30 more per month than Basic customers
# with the same income and age.
--- check
expect(inherits(fit, "lm"), "fit should be an lm model.")
expect(all(c("income", "age") %in% names(coef(fit))) && any(grepl("^plan", names(coef(fit)))), "Use monthly_spend ~ income + age + plan.")
expect(summary(fit)$r.squared > 0.8, "The training R-squared should be above 0.8.")
expect(is.numeric(rmse) && rmse > 3 && rmse < 9, paste("rmse looks wrong:", rmse))
expect(is.numeric(r2_test) && r2_test > 0.75 && r2_test < 1, paste("r2_test looks wrong:", r2_test))
CHECK_MESSAGE <- sprintf("Test R2 = %.3f, RMSE = %.2f.", r2_test, rmse)
--- hints
- `idx <- sample(nrow(df), round(0.75 * nrow(df)))`, then `df[idx, ]` and `df[-idx, ]`.
- `predict(fit, newdata = test)`
