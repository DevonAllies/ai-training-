id: explain-py-1
stage: explain
lang: python
title: SHAP by hand for a linear model
--- task
Fit `LinearRegression` on all customers predicting `monthly_spend` from
`income, age, tenure_months` (in that column order). Then compute **exact SHAP values by hand**:

* **`phi`** – a NumPy array of shape (600, 3): `coef × (x − column mean)`
* **`base`** – the base value: the mean prediction
* **`importance`** – a pandas Series: mean |φ| per feature, indexed by feature name, sorted descending

Verify **additivity** yourself: `base + phi.sum(axis=1)` should equal `model.predict(X)`.
--- starter
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

df = pd.read_csv("data/customers.csv")
features = ["income", "age", "tenure_months"]
X = df[features].to_numpy(float)
y = df["monthly_spend"]
model = LinearRegression().fit(X, y)

phi = None
base = None
importance = None
--- solution
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

df = pd.read_csv("data/customers.csv")
features = ["income", "age", "tenure_months"]
X = df[features].to_numpy(float)
y = df["monthly_spend"]
model = LinearRegression().fit(X, y)

phi = model.coef_ * (X - X.mean(axis=0))
base = model.predict(X).mean()
assert np.allclose(base + phi.sum(axis=1), model.predict(X))   # additivity holds

importance = pd.Series(np.abs(phi).mean(axis=0), index=features).sort_values(ascending=False)
print(importance.round(2))
print("Customer 0:", dict(zip(features, phi[0].round(2))), "base", round(base, 2))
--- check
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
d = pd.read_csv("data/customers.csv")
Xr = d[["income", "age", "tenure_months"]].to_numpy(float)
m = LinearRegression().fit(Xr, d["monthly_spend"])
phi_ = np.asarray(phi, dtype=float)
expect(phi_.shape == (600, 3), f"phi should have shape (600, 3), it has {phi_.shape}.")
expect(np.allclose(float(base) + phi_.sum(axis=1), m.predict(Xr), atol=1e-6),
       "Additivity fails: base + phi.sum(axis=1) should equal the predictions. Did you subtract the column means?")
expect(isinstance(importance, pd.Series) and list(importance.index)[0] == "income",
       "importance should be a Series of mean |phi| indexed by feature, sorted descending (income first).")
expect(abs(importance["income"] - np.abs(phi_[:, 0]).mean()) < 1e-6, "importance should be the mean of |phi| per column.")
CHECK_MESSAGE = "Exact SHAP values: they add up to every prediction. Income dominates spend."
--- hints
- NumPy broadcasting: `model.coef_ * (X - X.mean(axis=0))` multiplies each column by its coefficient.
- `np.abs(phi).mean(axis=0)` averages each column.
