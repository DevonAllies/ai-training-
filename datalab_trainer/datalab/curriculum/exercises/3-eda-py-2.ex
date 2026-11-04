id: eda-py-2
stage: eda
lang: python
title: Charts and a correlation matrix
--- task
Make **at least two charts** with matplotlib:

1. a **histogram** of `monthly_spend`,
2. a **box plot** of `monthly_spend` by `plan` (or a bar chart of churn rate by plan),

each with a title that states the message and labelled axes. Then compute

* **`corr`** – the correlation matrix (`DataFrame.corr()`) of
  `age, income, tenure_months, support_calls, monthly_spend, churned`.

Call `plt.show()` after each chart. DataLab saves the charts so you can use them in the Report Builder.
--- starter
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/customers.csv")

fig, ax = plt.subplots()
# TODO histogram of monthly_spend
plt.show()

corr = None
--- solution
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/customers.csv")

fig, ax = plt.subplots(figsize=(7, 4))
ax.hist(df["monthly_spend"], bins=30, color="#4c78a8", edgecolor="white")
ax.set(title="Half of customers spend 58-86 per month", xlabel="Monthly spend", ylabel="Customers")
plt.show()

fig, ax = plt.subplots(figsize=(7, 4))
order = ["Basic", "Standard", "Premium"]
ax.boxplot([df.loc[df.plan == p, "monthly_spend"] for p in order])
ax.set_xticks([1, 2, 3], order)
ax.set(title="Premium customers spend the most", xlabel="Plan", ylabel="Monthly spend")
plt.show()

cols = ["age", "income", "tenure_months", "support_calls", "monthly_spend", "churned"]
corr = df[cols].corr()
print(corr.round(2))
--- check
import matplotlib.pyplot as plt
import pandas as pd
import _datalab_mpl
n_figs = _datalab_mpl._count[0] + len([n for n in plt.get_fignums() if plt.figure(n).axes and plt.figure(n).axes[0].has_data()])
expect(n_figs >= 2, f"Make at least two charts (found {n_figs}).")
ref = pd.read_csv("data/customers.csv")[["age", "income", "tenure_months", "support_calls", "monthly_spend", "churned"]].corr()
expect(isinstance(corr, pd.DataFrame) and corr.shape == (6, 6), "corr should be a 6x6 correlation matrix of the listed columns.")
expect(abs(corr.loc["income", "monthly_spend"] - ref.loc["income", "monthly_spend"]) < 1e-9, "corr values don't match df[cols].corr().")
CHECK_MESSAGE = f"Charts saved. Strongest link: income vs spend (r = {ref.loc['income', 'monthly_spend']:.2f})."
--- hints
- `ax.hist(values, bins=30)` and `ax.set(title=..., xlabel=..., ylabel=...)`
- `ax.boxplot([group1, group2, group3])`
- `df[cols].corr()`
