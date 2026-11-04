id: stats-py-2
stage: stats
lang: python
title: Chi-square tests - which categories matter?
--- task
Is churn related to **plan**? Is it related to **region**?

For each, build a contingency table with `pd.crosstab(category, df["churned"])` and run
`scipy.stats.chi2_contingency`. Create:

* **`table_plan`**, **`chi2_plan`**, **`p_plan`**
* **`table_region`**, **`chi2_region`**, **`p_region`**
* **`conclusion`** – a dictionary `{"plan": True/False, "region": True/False}`: significant at α = 0.05?
--- starter
import pandas as pd
from scipy import stats

df = pd.read_csv("data/customers.csv")

table_plan = None
chi2_plan = p_plan = None
table_region = None
chi2_region = p_region = None
conclusion = {}
--- solution
import pandas as pd
from scipy import stats

df = pd.read_csv("data/customers.csv")

table_plan = pd.crosstab(df["plan"], df["churned"])
chi2_plan, p_plan, dof_plan, _ = stats.chi2_contingency(table_plan)
table_region = pd.crosstab(df["region"], df["churned"])
chi2_region, p_region, dof_region, _ = stats.chi2_contingency(table_region)
conclusion = {"plan": bool(p_plan < 0.05), "region": bool(p_region < 0.05)}
print(table_plan, f"plan:   chi2 = {chi2_plan:.1f}, p = {p_plan:.2g}", sep="\n")
print(table_region, f"region: chi2 = {chi2_region:.1f}, p = {p_region:.2f}", sep="\n")
--- check
import pandas as pd
from scipy import stats as _st
d = pd.read_csv("data/customers.csv")
rp = _st.chi2_contingency(pd.crosstab(d.plan, d.churned))
rr = _st.chi2_contingency(pd.crosstab(d.region, d.churned))
expect(isinstance(table_plan, pd.DataFrame) and table_plan.shape == (3, 2), "table_plan should be a 3 x 2 crosstab of plan by churned.")
expect(isinstance(table_region, pd.DataFrame) and table_region.shape == (4, 2), "table_region should be a 4 x 2 crosstab of region by churned.")
expect(abs(float(chi2_plan) - rp[0]) < 1e-6 and abs(float(p_plan) - rp[1]) < 1e-9, "chi2_plan / p_plan are wrong.")
expect(abs(float(chi2_region) - rr[0]) < 1e-6 and abs(float(p_region) - rr[1]) < 1e-9, "chi2_region / p_region are wrong.")
expect(conclusion == {"plan": True, "region": False}, "conclusion: plan is significant (p < 0.05), region is not.")
CHECK_MESSAGE = "Plan matters (p < 0.001). The regional gap that looked big in EDA is consistent with chance (p = 0.47)."
--- hints
- `chi2, p, dof, expected = stats.chi2_contingency(table)`
- Wrap comparisons in `bool(...)` so the dictionary holds plain True/False.
