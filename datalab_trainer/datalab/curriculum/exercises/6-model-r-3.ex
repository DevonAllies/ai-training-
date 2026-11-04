id: model-r-3
stage: model
lang: r
title: k-fold cross-validation by hand in R
level: 2
--- task
Write the cross-validation loop yourself, so you see exactly what `cross_val_score` does.

1. `set.seed(1)`; assign every customer to one of **5 folds**: `folds <- sample(rep(1:5, length.out = nrow(df)))`.
2. For each fold k: fit `glm(churned ~ tenure_months + support_calls + plan + age + income, family = binomial)`
   on the other folds, predict fold k, compute its AUC (rank formula from model-r-2).
3. **`cv_auc`** – the vector of 5 AUCs; **`cv_mean`** and **`cv_sd`** – their mean and standard deviation.

Repeat for a simpler model with only `tenure_months + support_calls`: **`cv_mean_simple`**. Is the bigger model worth it?
--- starter
df <- read.csv("data/customers.csv", stringsAsFactors = TRUE)
auc <- function(p, y) {
  n1 <- sum(y == 1); n0 <- sum(y == 0)
  (sum(rank(p)[y == 1]) - n1 * (n1 + 1) / 2) / (n1 * n0)
}
set.seed(1)

cv_auc <- NA
cv_mean <- NA
cv_sd <- NA
cv_mean_simple <- NA
--- solution
df <- read.csv("data/customers.csv", stringsAsFactors = TRUE)
auc <- function(p, y) {
  n1 <- sum(y == 1); n0 <- sum(y == 0)
  (sum(rank(p)[y == 1]) - n1 * (n1 + 1) / 2) / (n1 * n0)
}
set.seed(1)
folds <- sample(rep(1:5, length.out = nrow(df)))

cv <- function(formula) {
  sapply(1:5, function(k) {
    fit <- glm(formula, data = df[folds != k, ], family = binomial)
    p <- predict(fit, newdata = df[folds == k, ], type = "response")
    auc(p, df$churned[folds == k])
  })
}
cv_auc <- cv(churned ~ tenure_months + support_calls + plan + age + income)
cv_mean <- mean(cv_auc)
cv_sd <- sd(cv_auc)
cv_mean_simple <- mean(cv(churned ~ tenure_months + support_calls))
cat(sprintf("full model AUC %.3f (sd %.3f); simple model %.3f\n", cv_mean, cv_sd, cv_mean_simple))
--- check
expect(is.numeric(cv_auc) && length(cv_auc) == 5 && all(cv_auc > 0.6 & cv_auc <= 1), "cv_auc should hold 5 fold AUCs.")
expect(abs(cv_mean - mean(cv_auc)) < 1e-12 && abs(cv_sd - sd(cv_auc)) < 1e-12, "cv_mean and cv_sd should be mean() and sd() of cv_auc.")
expect(is.numeric(cv_mean_simple) && cv_mean_simple > 0.65 && cv_mean_simple < cv_mean + 0.05, paste("cv_mean_simple looks wrong:", cv_mean_simple))
CHECK_MESSAGE <- sprintf("Full model %.3f vs simple %.3f: the extra features add only %.3f AUC, within one fold-to-fold sd (%.3f). The simple model is nearly as good and easier to explain.", cv_mean, cv_mean_simple, cv_mean - cv_mean_simple, cv_sd)
--- hints
- `df[folds != k, ]` is the training part, `df[folds == k, ]` the held-out fold.
- `sapply(1:5, function(k) ...)` returns one number per fold.
