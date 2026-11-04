id: stats-py-3
stage: stats
lang: python
title: Bootstrap confidence intervals
level: 2
--- task
There's no simple formula for a confidence interval of a **median** or of a **difference in churn
rates**, so bootstrap them.

With `rng = np.random.default_rng(0)` and **2,000** resamples:

* **`ci_median_income`** – 95% CI for the median income (resample the income column with replacement)
* **`ci_diff`** – 95% CI for churn(Basic) − churn(Premium): resample *each group* separately, take the difference each time
* **`boots_diff`** – the array of 2,000 bootstrap differences

Plot a histogram of `boots_diff` with vertical lines at the interval limits. Does the interval include 0?
--- starter
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/customers.csv")
rng = np.random.default_rng(0)

ci_median_income = None
boots_diff = None
ci_diff = None
--- solution
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/customers.csv")
rng = np.random.default_rng(0)
B = 2000

income = df["income"].to_numpy()
meds = np.array([np.median(rng.choice(income, size=len(income), replace=True)) for _ in range(B)])
ci_median_income = tuple(np.percentile(meds, [2.5, 97.5]))

basic = df.loc[df.plan == "Basic", "churned"].to_numpy()
prem = df.loc[df.plan == "Premium", "churned"].to_numpy()
boots_diff = np.array([rng.choice(basic, len(basic)).mean() - rng.choice(prem, len(prem)).mean() for _ in range(B)])
ci_diff = tuple(np.percentile(boots_diff, [2.5, 97.5]))

fig, ax = plt.subplots(figsize=(7, 3.5))
ax.hist(boots_diff * 100, bins=40, color="#bbbbbb")
for v in ci_diff:
    ax.axvline(v * 100, color="#d1495b", linestyle="--")
ax.set(title="Basic churns about 20 points more than Premium",
       xlabel="Churn difference, Basic - Premium (percentage points)", ylabel="Bootstrap samples")
plt.show()
print("median income CI:", np.round(ci_median_income), " diff CI:", np.round(ci_diff, 3))
--- check
import numpy as np
import pandas as pd
d = pd.read_csv("data/customers.csv")
m = d["income"].median()
expect(len(ci_median_income) == 2 and ci_median_income[0] <= m <= ci_median_income[1], "ci_median_income should be (lower, upper) and contain the sample median.")
expect(1000 < ci_median_income[1] - ci_median_income[0] < 15000, "ci_median_income width looks wrong. Use the 2.5th and 97.5th percentiles of the bootstrap medians.")
bd = np.asarray(boots_diff)
expect(bd.shape == (2000,), "boots_diff should hold 2000 bootstrap differences.")
obs = d.loc[d.plan == "Basic", "churned"].mean() - d.loc[d.plan == "Premium", "churned"].mean()
expect(abs(bd.mean() - obs) < 0.01, "The bootstrap differences should be centred on the observed difference.")
expect(len(ci_diff) == 2 and ci_diff[0] < obs < ci_diff[1] and ci_diff[0] > 0, "ci_diff should be the 2.5/97.5 percentiles of boots_diff (and it shouldn't include 0).")
--- hints
- `rng.choice(x, size=len(x), replace=True)` draws one bootstrap sample.
- `np.percentile(values, [2.5, 97.5])`
- Resample Basic and Premium separately inside the same loop.
