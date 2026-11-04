id: stats-py-1
stage: stats
lang: python
title: t-tests - churners vs stayers
--- task
Use `scipy.stats.ttest_ind(..., equal_var=False)` (Welch's t-test) to compare churners (`churned == 1`)
with stayers on two variables:

* **`t_tenure`, `p_tenure`** – for `tenure_months`
* **`t_spend`, `p_spend`** – for `monthly_spend`
* **`diff_tenure`** – mean tenure of churners minus stayers (months)

Then set **`tenure_significant`** and **`spend_significant`** to `True`/`False` using α = 0.05.
Which difference matters more *in practice*?
--- starter
import pandas as pd
from scipy import stats

df = pd.read_csv("data/customers.csv")
churners = df[df["churned"] == 1]
stayers = df[df["churned"] == 0]

t_tenure = p_tenure = None
t_spend = p_spend = None
diff_tenure = None
tenure_significant = spend_significant = None
--- solution
import pandas as pd
from scipy import stats

df = pd.read_csv("data/customers.csv")
churners = df[df["churned"] == 1]
stayers = df[df["churned"] == 0]

t_tenure, p_tenure = stats.ttest_ind(churners["tenure_months"], stayers["tenure_months"], equal_var=False)
t_spend, p_spend = stats.ttest_ind(churners["monthly_spend"], stayers["monthly_spend"], equal_var=False)
diff_tenure = churners["tenure_months"].mean() - stayers["tenure_months"].mean()
tenure_significant = p_tenure < 0.05
spend_significant = p_spend < 0.05
print(f"Tenure: churners {diff_tenure:+.1f} months, t = {t_tenure:.1f}, p = {p_tenure:.2g}")
print(f"Spend:  t = {t_spend:.2f}, p = {p_spend:.3f}")
# Tenure: a huge, very clear gap. Spend: a small (about 4 per month) and only borderline difference.
--- check
from scipy import stats as _st
import pandas as pd
d = pd.read_csv("data/customers.csv")
c, s = d[d.churned == 1], d[d.churned == 0]
tt = _st.ttest_ind(c.tenure_months, s.tenure_months, equal_var=False)
ts = _st.ttest_ind(c.monthly_spend, s.monthly_spend, equal_var=False)
expect(t_tenure is not None and abs(float(t_tenure) - tt.statistic) < 1e-6, "t_tenure is wrong. Use ttest_ind(churners, stayers, equal_var=False) on tenure_months.")
expect(abs(float(p_tenure) - tt.pvalue) < 1e-9, "p_tenure is wrong.")
expect(abs(float(t_spend) - ts.statistic) < 1e-6 and abs(float(p_spend) - ts.pvalue) < 1e-9, "t_spend / p_spend are wrong.")
expect(abs(diff_tenure - (c.tenure_months.mean() - s.tenure_months.mean())) < 1e-9, "diff_tenure should be churners' mean minus stayers' mean.")
expect(bool(tenure_significant) == (tt.pvalue < 0.05) and bool(spend_significant) == (ts.pvalue < 0.05), "Set the *_significant flags with p < 0.05.")
CHECK_MESSAGE = f"Churners have {abs(diff_tenure):.0f} months less tenure (p < 0.001); the spend gap is small and borderline (p = {ts.pvalue:.3f})."
--- hints
- `t, p = stats.ttest_ind(a, b, equal_var=False)`
- `equal_var=False` gives Welch's test, which doesn't assume equal variances (the safer default).
