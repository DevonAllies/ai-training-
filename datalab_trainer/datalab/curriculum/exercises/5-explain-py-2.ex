id: explain-py-2
stage: explain
lang: python
title: Explain a random forest with the shap package
needs: shap
--- task
Fit `RandomForestClassifier(n_estimators=200, max_depth=6, random_state=0)` to predict
`churned` from `tenure_months, support_calls, monthly_fee, age, income`, then use
**`shap.TreeExplainer`** to explain it.

* **`sv`** – SHAP values for the **churn class (1)** as a NumPy array of shape (600, 5)
* **`importance`** – Series of mean |SHAP| per feature, sorted descending
* make a **beeswarm** (`shap.summary_plot(sv, X)` or `shap.plots.beeswarm`) and a **bar** chart of `importance`

In a comment, write which two features drive churn risk and in which direction.

*Needs the `shap` package: `pip install shap` in DataLab's environment (the installer adds it).*
--- starter
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
import shap

df = pd.read_csv("data/customers.csv")
features = ["tenure_months", "support_calls", "monthly_fee", "age", "income"]
X, y = df[features], df["churned"]
rf = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=0).fit(X, y)

sv = None
importance = None
--- solution
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
import shap

df = pd.read_csv("data/customers.csv")
features = ["tenure_months", "support_calls", "monthly_fee", "age", "income"]
X, y = df[features], df["churned"]
rf = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=0).fit(X, y)

explainer = shap.TreeExplainer(rf)
values = explainer.shap_values(X)
# Older shap versions return a list [class0, class1]; newer ones a (rows, features, classes) array
sv = values[1] if isinstance(values, list) else values[..., 1]

importance = pd.Series(np.abs(sv).mean(axis=0), index=features).sort_values(ascending=False)
print(importance.round(4))

shap.summary_plot(sv, X, show=False)
plt.title("What drives churn risk (SHAP)")
plt.show()

fig, ax = plt.subplots(figsize=(6, 3.5))
importance.sort_values().plot.barh(ax=ax, color="#4c78a8")
ax.set(title="Support calls and tenure drive churn risk", xlabel="mean |SHAP value| (churn probability)")
plt.show()
# More support calls -> higher risk; longer tenure -> lower risk.
--- check
import numpy as np
import pandas as pd
sv_ = np.asarray(sv, dtype=float)
expect(sv_.shape == (600, 5), f"sv should have shape (600, 5) for class 1, it has {sv_.shape}. For a (600, 5, 2) array use sv[..., 1].")
expect(isinstance(importance, pd.Series) and len(importance) == 5, "importance should be a Series with 5 features.")
expect(list(importance.index[:2]) in (["support_calls", "tenure_months"], ["tenure_months", "support_calls"]),
       f"The top two features should be support_calls and tenure_months; you have {list(importance.index[:2])}.")
i_calls = list(X.columns).index("support_calls")
expect(np.corrcoef(X["support_calls"], sv_[:, i_calls])[0, 1] > 0.5, "SHAP values for support_calls should rise with the number of calls. Did you take class 1?")
CHECK_MESSAGE = "SHAP shows support calls push risk up and long tenure pulls it down, matching the EDA."
--- hints
- `explainer = shap.TreeExplainer(rf)`; `values = explainer.shap_values(X)`
- For a binary classifier take the churn class: `values[..., 1]` (or `values[1]` in old versions).
- `shap.summary_plot(sv, X, show=False)` then `plt.show()`.
