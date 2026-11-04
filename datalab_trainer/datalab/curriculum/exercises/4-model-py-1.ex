id: model-py-1
stage: model
lang: python
title: Linear regression with a train/test split
--- task
Predict **`monthly_spend`** from `income`, `age` and `plan`.

1. Build `X` with `pd.get_dummies(..., columns=["plan"], drop_first=True, dtype=float)` and `y`.
2. Split with `train_test_split(X, y, test_size=0.25, random_state=42)`.
3. Fit a `LinearRegression` called **`model`** on the training set.
4. On the **test** set compute **`r2`** (R²) and **`rmse`**.
5. Compute **`baseline_rmse`**: the RMSE when you always predict the *training* mean.

Print the coefficients. How much better than the baseline is the model?
--- starter
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_squared_error

df = pd.read_csv("data/customers.csv")

X = None
y = None

model = None
r2 = None
rmse = None
baseline_rmse = None
--- solution
import numpy as np
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
r2 = r2_score(y_test, pred)
rmse = mean_squared_error(y_test, pred) ** 0.5
baseline_rmse = float(np.sqrt(((y_test - y_train.mean()) ** 2).mean()))

print(pd.Series(model.coef_, index=X.columns).round(5))
print(f"R2 = {r2:.3f}, RMSE = {rmse:.2f}, baseline RMSE = {baseline_rmse:.2f}")
--- check
import numpy as np
expect(hasattr(model, "coef_"), "model should be a fitted LinearRegression.")
expect(model.n_features_in_ == 4, f"The model should use 4 features (income, age, plan_Premium, plan_Standard); it uses {model.n_features_in_}.")
expect(0.8 < r2 <= 1, f"r2 should be about 0.85 on the test set; you have {r2:.3f}. Did you use test_size=0.25, random_state=42?")
expect(4 < rmse < 8, f"rmse looks wrong ({rmse:.2f}). It's sqrt(mean_squared_error(y_test, pred)).")
expect(baseline_rmse > 2 * rmse, "baseline_rmse should be the RMSE of always predicting y_train.mean() on the test set.")
CHECK_MESSAGE = f"R2 = {r2:.3f}. The model's errors are {(1 - rmse / baseline_rmse):.0%} smaller than the baseline's."
--- hints
- `train_test_split(X, y, test_size=0.25, random_state=42)` returns X_train, X_test, y_train, y_test.
- `mean_squared_error(y_test, pred) ** 0.5` is RMSE.
- Baseline: `np.sqrt(((y_test - y_train.mean()) ** 2).mean())`
