id: model-py-3
stage: model
lang: python
title: Compare models with cross-validation
level: 2
--- task
Compare a **logistic regression** pipeline with a **random forest** using **5-fold
cross-validated ROC AUC** on all 600 customers.

* `cv_logit` – array of 5 AUC scores for the logistic pipeline
* `cv_rf` – array of 5 AUC scores for `RandomForestClassifier(n_estimators=300, max_depth=5, random_state=0)`
  (trees don't need scaling; one-hot encoding is enough)
* `best` – the string `"logistic"` or `"forest"`, whichever has the higher mean

Use `StratifiedKFold(5, shuffle=True, random_state=1)` for both so they're tested on the same folds.
Is the more complex model worth it?
--- starter
import pandas as pd
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

df = pd.read_csv("data/customers.csv")
num = ["tenure_months", "support_calls", "monthly_fee", "age", "income"]
cat = ["plan", "region"]

cv_logit = None
cv_rf = None
best = None
--- solution
import pandas as pd
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

df = pd.read_csv("data/customers.csv")
num = ["tenure_months", "support_calls", "monthly_fee", "age", "income"]
cat = ["plan", "region"]
X, y = df[num + cat], df["churned"]
folds = StratifiedKFold(5, shuffle=True, random_state=1)

logit = make_pipeline(ColumnTransformer([("num", StandardScaler(), num),
                                         ("cat", OneHotEncoder(drop="first"), cat)]),
                      LogisticRegression(max_iter=1000))
forest = make_pipeline(ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), cat)],
                                         remainder="passthrough"),
                       RandomForestClassifier(n_estimators=300, max_depth=5, random_state=0))

cv_logit = cross_val_score(logit, X, y, cv=folds, scoring="roc_auc")
cv_rf = cross_val_score(forest, X, y, cv=folds, scoring="roc_auc")
best = "logistic" if cv_logit.mean() >= cv_rf.mean() else "forest"
print(f"logistic {cv_logit.mean():.3f} ± {cv_logit.std():.3f}")
print(f"forest   {cv_rf.mean():.3f} ± {cv_rf.std():.3f}  -> best: {best}")
--- check
import numpy as np
cv_logit, cv_rf = np.asarray(cv_logit), np.asarray(cv_rf)
expect(cv_logit.shape == (5,) and cv_rf.shape == (5,), "cv_logit and cv_rf should each hold 5 fold scores.")
expect(0.7 < cv_logit.mean() < 1 and 0.65 < cv_rf.mean() < 1, "Scores look wrong. Use scoring='roc_auc'.")
expect(best == ("logistic" if cv_logit.mean() >= cv_rf.mean() else "forest"), "best should name the model with the higher mean AUC.")
CHECK_MESSAGE = (f"logistic {cv_logit.mean():.3f} vs forest {cv_rf.mean():.3f}. The true churn process here is close to "
                 "logistic, so the simple model is hard to beat. In real data, always try both.")
--- hints
- `cross_val_score(model, X, y, cv=folds, scoring="roc_auc")`
- For the forest: `ColumnTransformer([("cat", OneHotEncoder(), cat)], remainder="passthrough")`
