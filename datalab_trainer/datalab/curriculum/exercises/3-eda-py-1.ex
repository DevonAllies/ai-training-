id: eda-py-1
stage: eda
lang: python
title: Summaries and group comparisons with pandas
--- task
Load **`data/customers.csv`** into `df`, then create:

* **`summary`** – `df.describe()` of the numeric columns,
* **`rates`** – a Series of churn rate by `plan` (index = plan), sorted from highest to lowest,
* **`spend_by_region`** – mean `monthly_spend` per `region`,
* **`calls_rates`** – churn rate by number of support-call band: use `pd.cut(df.support_calls, [-1, 1, 3, 100], labels=["0-1", "2-3", "4+"])`.

Print them and write one sentence (as a comment) about what you notice.
--- starter
import pandas as pd

df = pd.read_csv("data/customers.csv")

summary = None
rates = None
spend_by_region = None
calls_rates = None
--- solution
import pandas as pd

df = pd.read_csv("data/customers.csv")

summary = df.describe()
rates = df.groupby("plan")["churned"].mean().sort_values(ascending=False)
spend_by_region = df.groupby("region")["monthly_spend"].mean()
bands = pd.cut(df["support_calls"], [-1, 1, 3, 100], labels=["0-1", "2-3", "4+"])
calls_rates = df.groupby(bands, observed=True)["churned"].mean()

print(summary.round(2), rates.round(3), spend_by_region.round(2), calls_rates.round(3), sep="\n\n")
# Basic customers churn almost 3x as often as Premium; churn climbs steeply with support calls.
--- check
import pandas as pd
ref = pd.read_csv("data/customers.csv")
expect(isinstance(summary, pd.DataFrame) and "mean" in summary.index, "summary should be df.describe().")
exp = ref.groupby("plan")["churned"].mean().sort_values(ascending=False)
expect(isinstance(rates, pd.Series), "rates should be a pandas Series.")
expect(list(rates.index) == list(exp.index), f"rates should be sorted high to low: expected order {list(exp.index)}.")
expect(((rates - exp).abs() < 1e-9).all(), "rates values are wrong: use groupby('plan')['churned'].mean().")
sr = ref.groupby("region")["monthly_spend"].mean()
expect(((spend_by_region.reindex(sr.index) - sr).abs() < 1e-9).all(), "spend_by_region should be the mean monthly_spend per region.")
b = pd.cut(ref["support_calls"], [-1, 1, 3, 100], labels=["0-1", "2-3", "4+"])
cr = ref.groupby(b, observed=True)["churned"].mean()
expect(len(calls_rates) == 3 and all(abs(float(calls_rates[k]) - cr[k]) < 1e-9 for k in cr.index),
       "calls_rates should be churn rate per band 0-1 / 2-3 / 4+.")
CHECK_MESSAGE = f"Correct. Churn goes from {cr.iloc[0]:.0%} (0-1 calls) to {cr.iloc[-1]:.0%} (4+ calls). That's a lead to follow up."
--- hints
- `df.groupby("plan")["churned"].mean()` then `.sort_values(ascending=False)`
- `df.groupby(bands, observed=True)["churned"].mean()` groups by the band Series.
