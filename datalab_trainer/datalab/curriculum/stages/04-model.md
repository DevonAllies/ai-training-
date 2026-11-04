id: model
title: Model
summary: Features, train/test splits, regression and classification, and honest evaluation.
--- lesson
# Stage 4 · Modelling

A model is a rule learned from data that **predicts** a target from inputs (features).
Ridgeway has two modelling questions:

| Question | Target | Type | Baseline model |
|---|---|---|---|
| How much will a customer spend per month? | `monthly_spend` (number) | **regression** | linear regression |
| Will a customer churn? | `churned` (0/1) | **classification** | logistic regression |

## The modelling workflow

1. **Define the target and the features.** Use only features you would know *at prediction time*. Leaving one in that you wouldn't know then is called *leakage*.
2. **Split** into a training set (fit) and a test set (evaluate) — e.g. 75/25 with a fixed random seed.
3. **Prepare features**: one-hot encode categories, scale numbers if the model needs it. Fit this preparation on the **training set only**.
4. **Fit a simple baseline**, then try something more flexible (e.g. random forest).
5. **Evaluate on the test set** with a metric that matches the business question.
6. **Check** residuals and errors, and compare against a naive baseline (e.g. always predict the mean).

## Metrics

| Regression | Meaning |
|---|---|
| **RMSE** | typical size of an error, in the target's units (lower is better) |
| **MAE** | average absolute error — less sensitive to outliers |
| **R²** | share of variance explained (1 = perfect, 0 = no better than the mean) |

| Classification | Meaning |
|---|---|
| **Accuracy** | share predicted correctly. Misleading when classes are imbalanced (77% stay!) |
| **Precision / Recall** | of predicted churners, how many churned? of real churners, how many did we catch? |
| **ROC AUC** | probability a random churner is ranked above a random stayer (0.5 = coin flip) |

## Linear regression

```sql
-- SQL can fit a one-feature regression with aggregate functions
SELECT regr_slope(monthly_spend, income)     AS slope,
       regr_intercept(monthly_spend, income) AS intercept,
       regr_r2(monthly_spend, income)        AS r2
FROM customers;
```
```python
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_squared_error

df = pd.read_csv("data/customers.csv")
X = pd.get_dummies(df[["income", "age", "plan"]], columns=["plan"], drop_first=True, dtype=float)
y = df["monthly_spend"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)
model = LinearRegression().fit(X_train, y_train)
pred = model.predict(X_test)
print("R2:", r2_score(y_test, pred), "RMSE:", mean_squared_error(y_test, pred) ** 0.5)
print(dict(zip(X.columns, model.coef_.round(4))))
```
```r
df <- read.csv("data/customers.csv", stringsAsFactors = TRUE)
set.seed(42)
idx <- sample(nrow(df), 0.75 * nrow(df))
train <- df[idx, ]; test <- df[-idx, ]
fit <- lm(monthly_spend ~ income + age + plan, data = train)
summary(fit)                      # coefficients, p-values, R-squared
pred <- predict(fit, newdata = test)
sqrt(mean((test$monthly_spend - pred)^2))   # RMSE
```

**Reading coefficients:** each extra 1,000 of income adds about `1000 × coef` to monthly
spend, *holding the other features fixed*. The coefficient for a category such as `plan`
is the difference compared with the reference level (Basic).

## Logistic regression and a random forest

```python
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score

num = ["tenure_months", "support_calls", "monthly_fee", "age", "income"]
cat = ["plan", "region"]
X, y = df[num + cat], df["churned"]
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
prep = ColumnTransformer([("num", StandardScaler(), num),
                          ("cat", OneHotEncoder(drop="first"), cat)])
logit = make_pipeline(prep, LogisticRegression(max_iter=1000)).fit(X_tr, y_tr)
print("AUC logistic:", roc_auc_score(y_te, logit.predict_proba(X_te)[:, 1]))
```
```r
fit <- glm(churned ~ tenure_months + support_calls + plan + age + income,
           data = train, family = binomial)
summary(fit)
p <- predict(fit, newdata = test, type = "response")   # probabilities
table(predicted = p > 0.5, actual = test$churned)       # confusion matrix
```

Logistic coefficients are in **log-odds**: `exp(coef)` is the odds ratio. An odds ratio
of 1.8 for `support_calls` means each extra call multiplies the odds of churning by 1.8.

## Cross-validation

One test split can be lucky or unlucky. **k-fold cross-validation** fits k models, each
tested on a different fold, and averages the score. This gives a more stable estimate for
comparing models.

```python
from sklearn.model_selection import cross_val_score
scores = cross_val_score(logit, X, y, cv=5, scoring="roc_auc")
print(scores.mean(), scores.std())
```

> **Pitfalls**: leakage (features from the future), tuning on the test set, reporting
> accuracy on imbalanced data, and forgetting that a model only finds associations in the
> data. It doesn't tell you what causes what.
--- quiz
Q: Why must the scaler / encoder be fitted on the training set only?
- It is faster
* Otherwise information from the test set leaks into training and the test score is too optimistic
- scikit-learn requires it
E: The test set must imitate unseen future data. Anything learned from it, even a mean, is leakage.
Q: 77% of customers do not churn. A model that predicts "no churn" for everyone has accuracy of…
- 23%
- 50%
* 77%
E: Which is why accuracy alone is misleading on imbalanced data. Use AUC, precision and recall.
Q: An R² of 0.80 on the test set means…
- The model is right 80% of the time
* The model explains 80% of the variance in the target on unseen data
- 80% of the coefficients are significant
E: R² compares squared errors with those of always predicting the mean.
Q: Which feature would be leakage when predicting churn next month?
- tenure_months
- plan
* the date the customer cancelled
- support_calls in the last quarter
E: A cancellation date only exists after churn has happened.
Q: ROC AUC of 0.5 means…
* The model ranks churners no better than a coin flip
- Half of the predictions are correct
- The model is perfect
E: AUC is about ranking: 1.0 is perfect separation, 0.5 is random.
