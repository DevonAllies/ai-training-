id: model-py-2
stage: model
lang: python
title: Logistic regression for churn with a pipeline
--- task
Predict **`churned`** with a scikit-learn **pipeline** so that scaling and encoding are
learned from the training data only.

* numeric features: `tenure_months, support_calls, monthly_fee, age, income`
* categorical features: `plan, region`
* split: `test_size=0.25, random_state=42, stratify=y`

Create **`model`** (a fitted Pipeline with a `LogisticRegression`), **`auc`** (ROC AUC on the
test set, using `predict_proba`) and **`cm`** (confusion matrix at threshold 0.5).
--- starter
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, confusion_matrix

df = pd.read_csv("data/customers.csv")
num = ["tenure_months", "support_calls", "monthly_fee", "age", "income"]
cat = ["plan", "region"]

model = None
auc = None
cm = None
--- solution
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, confusion_matrix

df = pd.read_csv("data/customers.csv")
num = ["tenure_months", "support_calls", "monthly_fee", "age", "income"]
cat = ["plan", "region"]
X, y = df[num + cat], df["churned"]
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

prep = ColumnTransformer([("num", StandardScaler(), num),
                          ("cat", OneHotEncoder(drop="first"), cat)])
model = make_pipeline(prep, LogisticRegression(max_iter=1000)).fit(X_tr, y_tr)

p = model.predict_proba(X_te)[:, 1]
auc = roc_auc_score(y_te, p)
cm = confusion_matrix(y_te, (p >= 0.5).astype(int))
print(f"AUC = {auc:.3f}")
print(cm)
--- check
import numpy as np
expect(hasattr(model, "predict_proba") and hasattr(model, "steps"), "model should be a fitted Pipeline (make_pipeline).")
expect(0.75 < auc < 1, f"auc should be around 0.8; you have {auc:.3f}. Use predict_proba(X_test)[:, 1], not predict().")
cm = np.asarray(cm)
expect(cm.shape == (2, 2) and cm.sum() == 150, "cm should be a 2x2 confusion matrix of the 150 test customers.")
CHECK_MESSAGE = f"AUC = {auc:.3f}: a random churner gets a higher risk score than a random stayer {auc:.0%} of the time."
--- hints
- `ColumnTransformer([("num", StandardScaler(), num), ("cat", OneHotEncoder(drop="first"), cat)])`
- `make_pipeline(prep, LogisticRegression(max_iter=1000)).fit(X_tr, y_tr)`
- `roc_auc_score(y_te, model.predict_proba(X_te)[:, 1])`
