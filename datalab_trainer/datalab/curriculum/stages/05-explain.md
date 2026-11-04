id: explain
title: Explain & Shape (SHAP)
summary: Explain models with SHAP values, then shape results into tables a reader can act on.
--- lesson
# Stage 5 · Explain & Shape

A model that nobody understands won't be trusted or used. This stage has two parts:

1. **Explain** the model: *which features matter, in which direction, for whom?* → **SHAP values**
2. **Shape** the results: pivot, rank and summarise them into tables for the report.

## SHAP in one paragraph

SHAP (SHapley Additive exPlanations) splits **one prediction** into a contribution from each
feature:

```
prediction = base value + φ(tenure) + φ(support_calls) + φ(plan) + …
```

The **base value** is the average prediction. Each φ ("phi") says how much that feature
pushed *this* customer's prediction up or down from the average. The idea comes from
Shapley values in game theory: features are "players" sharing the "payout" (the
prediction) fairly.

Three properties make SHAP useful:
* **Additive** — the contributions always add up exactly to the prediction.
* **Local → global** — average `|φ|` over all customers gives a global feature importance.
* **Direction** — the sign shows whether a feature raised or lowered the prediction.

## SHAP by hand for a linear model

For a linear model `f(x) = b + Σ wⱼ xⱼ` with independent features, the SHAP value is exact
and simple:

```
φⱼ(x) = wⱼ · (xⱼ − mean(xⱼ))          base value = mean prediction
```

This is a great way to *understand* SHAP before using a library:

```python
import numpy as np
from sklearn.linear_model import LinearRegression
X = df[["income", "age", "tenure_months"]].to_numpy(float)
m = LinearRegression().fit(X, df["monthly_spend"])
phi = m.coef_ * (X - X.mean(axis=0))          # one row per customer, one column per feature
base = m.predict(X).mean()
assert np.allclose(base + phi.sum(axis=1), m.predict(X))   # additivity!
importance = np.abs(phi).mean(axis=0)          # global importance
```
```r
fit <- lm(monthly_spend ~ income + age + tenure_months, data = df)
X <- as.matrix(df[, c("income", "age", "tenure_months")])
phi <- sweep(X, 2, colMeans(X)) %*% diag(coef(fit)[-1])
base <- mean(fitted(fit))
all.equal(unname(base + rowSums(phi)), unname(fitted(fit)))   # TRUE
colMeans(abs(phi))
```

## SHAP for any model with the `shap` package

For tree models (random forest, gradient boosting) `shap.TreeExplainer` computes exact
SHAP values fast. Other models can use `shap.Explainer` (sampling-based approximation).

```python
import shap
from sklearn.ensemble import RandomForestClassifier
X = pd.get_dummies(df[num + cat], drop_first=True, dtype=float)
rf = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=0).fit(X, df["churned"])
explainer = shap.TreeExplainer(rf)
sv = explainer(X)                     # Explanation object: values, base_values, data
sv = sv[:, :, 1]                      # class 1 = churn
shap.plots.beeswarm(sv)               # global: importance + direction
shap.plots.waterfall(sv[0])           # local: one customer's prediction explained
```
```r
# install.packages(c("kernelshap", "shapviz"))
library(kernelshap); library(shapviz)
fit <- glm(churned ~ tenure_months + support_calls + age + income, data = df, family = binomial)
X <- df[, c("tenure_months", "support_calls", "age", "income")]
ks <- kernelshap(fit, X = X[1:200, ], bg_X = X[sample(nrow(X), 100), ], type = "response")
sv <- shapviz(ks)
sv_importance(sv, kind = "beeswarm")
```

### How to read the plots

* **Beeswarm**: one dot per customer per feature. Position = SHAP value (effect on the
  prediction), colour = feature value. *Red dots far right for support_calls* → many calls
  push churn risk up.
* **Waterfall**: starts at the base value and adds each feature's push for one customer.
  Use it to explain one decision to a stakeholder ("this customer is high risk mainly
  because of 5 support calls and only 3 months' tenure").

### Cautions

* SHAP explains **the model**, not the world. A big SHAP value is not proof of cause and effect.
* Correlated features share credit in ways that can surprise you (e.g. `plan` and `monthly_fee`).
* Explanations are only as good as the model. Check the test-set performance first.

## Shaping results for people

Models and EDA produce long, narrow results. Readers want **compact, sorted, labelled tables**.

**Long → wide (pivot)**: churn rate by region (rows) × plan (columns).

```sql
PIVOT (SELECT region, plan, churned FROM customers)
ON plan USING round(avg(churned), 3) GROUP BY region ORDER BY region;
```
```python
pd.pivot_table(df, values="churned", index="region", columns="plan", aggfunc="mean").round(3)
```
```r
round(tapply(df$churned, list(df$region, df$plan), mean), 3)
# or reshape(), or tidyr::pivot_wider()
```

**Wide → long (melt / unpivot)** is the reverse — the shape most plotting libraries want.

```sql
UNPIVOT (SELECT customer_id, age, income FROM customers) ON age, income INTO NAME variable VALUE value;
```
```python
df.melt(id_vars="customer_id", value_vars=["age", "income"], var_name="variable")
```
```r
stack(df[, c("age", "income")])   # or tidyr::pivot_longer()
```

**Bins → segments**: cut a number into groups (`pd.cut`, `cut()`, `CASE WHEN`) so
results read as *"customers with 0–1 / 2–3 / 4+ support calls"*.

**Ranking**: sort by what matters, keep the top N, and add percentages and totals.
--- quiz
Q: For one customer the base value is 0.22, φ(support_calls) = +0.25, φ(tenure) = +0.10, all others sum to −0.07. What is the model's prediction?
- 0.22
- 0.35
* 0.50
- 0.57
E: SHAP is additive: 0.22 + 0.25 + 0.10 − 0.07 = 0.50.
Q: How do you turn per-customer SHAP values into a global feature importance?
- Sum the raw SHAP values
* Average the absolute SHAP values per feature
- Take the maximum SHAP value
E: Absolute values stop positive and negative effects from cancelling out.
Q: A feature has large SHAP values. Can you conclude that changing it will change churn?
- Yes, SHAP shows causality
* No, SHAP explains what the model relies on, not what causes churn
E: Model explanations reflect associations in the training data.
Q: Which operation turns a long table (region, plan, rate) into a region × plan grid?
* Pivot (long to wide)
- Melt (wide to long)
- Join
- Union
E: Pivoting spreads one column's values into new columns.
