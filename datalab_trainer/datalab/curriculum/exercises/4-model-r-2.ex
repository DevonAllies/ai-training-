id: model-r-2
stage: model
lang: r
title: Logistic regression with glm() and AUC by hand
--- task
Model churn with **`glm(..., family = binomial)`** using
`tenure_months + support_calls + plan + age + income` on a 75% training split (`set.seed(42)`).

Then on the test set compute:

* **`p`** – predicted probabilities (`type = "response"`)
* **`auc`** – ROC AUC **without a package**, using the rank (Mann-Whitney) formula:
  `(sum(rank(p)[y == 1]) - n1 * (n1 + 1) / 2) / (n1 * n0)`
* **`odds_calls`** – the odds ratio for one extra support call: `exp(coef(fit)["support_calls"])`
--- starter
df <- read.csv("data/customers.csv", stringsAsFactors = TRUE)
set.seed(42)

fit <- NA
p <- NA
auc <- NA
odds_calls <- NA
--- solution
df <- read.csv("data/customers.csv", stringsAsFactors = TRUE)
set.seed(42)
idx <- sample(nrow(df), round(0.75 * nrow(df)))
train <- df[idx, ]
test <- df[-idx, ]

fit <- glm(churned ~ tenure_months + support_calls + plan + age + income,
           data = train, family = binomial)
print(summary(fit))

p <- predict(fit, newdata = test, type = "response")
y <- test$churned
n1 <- sum(y == 1); n0 <- sum(y == 0)
auc <- (sum(rank(p)[y == 1]) - n1 * (n1 + 1) / 2) / (n1 * n0)
odds_calls <- unname(exp(coef(fit)["support_calls"]))
print(table(predicted = p > 0.5, actual = y))
cat("AUC:", round(auc, 3), " odds ratio per support call:", round(odds_calls, 2), "\n")
--- check
expect(inherits(fit, "glm") && fit$family$family == "binomial", "fit should be glm(..., family = binomial).")
expect(is.numeric(p) && all(p >= 0 & p <= 1) && length(p) == 150, "p should be 150 test-set probabilities (type = \"response\").")
expect(is.numeric(auc) && auc > 0.72 && auc <= 1, paste("auc looks wrong:", auc))
expect(is.numeric(odds_calls) && odds_calls > 1.3, "odds_calls should be exp() of the support_calls coefficient (about 1.8).")
CHECK_MESSAGE <- sprintf("AUC = %.3f. Each extra support call multiplies the odds of churn by %.2f.", auc, odds_calls)
--- hints
- `predict(fit, newdata = test, type = "response")` gives probabilities.
- `rank(p)[y == 1]` are the ranks of the real churners.
