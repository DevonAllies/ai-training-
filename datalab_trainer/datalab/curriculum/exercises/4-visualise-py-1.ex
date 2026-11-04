id: visualise-py-1
stage: visualise
lang: python
title: The right chart for each question (small multiples)
--- task
Make **one figure with a 2 × 2 grid** (`fig, axes = plt.subplots(2, 2, figsize=(11, 8))`), with the right
chart type in each panel:

1. top-left: **distribution** of `monthly_spend` → histogram
2. top-right: **churn rate by plan** → bar chart, sorted
3. bottom-left: **monthly revenue over time** (from `orders`) → line chart
4. bottom-right: **income vs monthly spend** → scatter plot

Every panel needs a **title** and **axis labels**. Keep the figure in a variable called **`fig`**.
--- starter
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/customers.csv")
orders = pd.read_csv("data/orders.csv", parse_dates=["order_date"])
orders["revenue"] = orders.quantity * orders.unit_price * (1 - orders.discount)

fig, axes = plt.subplots(2, 2, figsize=(11, 8))
# axes[0, 0] ... axes[1, 1]

plt.show()
--- solution
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/customers.csv")
orders = pd.read_csv("data/orders.csv", parse_dates=["order_date"])
orders["revenue"] = orders.quantity * orders.unit_price * (1 - orders.discount)

rates = df.groupby("plan")["churned"].mean().sort_values(ascending=False) * 100
monthly = orders.set_index("order_date")["revenue"].resample("MS").sum()

fig, axes = plt.subplots(2, 2, figsize=(11, 8))
ax = axes[0, 0]
ax.hist(df["monthly_spend"], bins=30, color="#4c78a8", edgecolor="white")
ax.set(title="Half of customers spend 58-86 a month", xlabel="Monthly spend", ylabel="Customers")
ax = axes[0, 1]
ax.bar(rates.index, rates.values, color="#4c78a8")
ax.set(title="Basic customers churn most", xlabel="Plan", ylabel="Churn rate (%)")
ax = axes[1, 0]
ax.plot(monthly.index, monthly.values, color="#4c78a8")
ax.set(title="Revenue has grown every year", xlabel="Month", ylabel="Revenue")
ax = axes[1, 1]
ax.scatter(df["income"], df["monthly_spend"], s=8, alpha=0.4, color="#4c78a8")
ax.set(title="Spend rises with income", xlabel="Income", ylabel="Monthly spend")
for a in axes.flat:
    a.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
plt.show()
--- check
from matplotlib.collections import PathCollection
from matplotlib.patches import Rectangle
expect("fig" in dir() and hasattr(fig, "axes"), "Keep the figure in a variable called fig.")
axs = [a for a in fig.axes if a.has_data()]
expect(len(axs) == 4, f"The figure should have 4 panels with data; it has {len(axs)}.")
for a in axs:
    expect(a.get_title().strip() != "", "Every panel needs a title (ax.set_title or ax.set(title=...)).")
    expect(a.get_xlabel().strip() != "" and a.get_ylabel().strip() != "", f"Panel '{a.get_title()}' needs both axis labels.")
kinds = set()
for a in axs:
    if any(isinstance(c, PathCollection) for c in a.collections):
        kinds.add("scatter")
    elif a.lines:
        kinds.add("line")
    elif len([p for p in a.patches if isinstance(p, Rectangle)]) > 5:
        kinds.add("hist")
    elif a.patches:
        kinds.add("bar")
expect(kinds == {"scatter", "line", "hist", "bar"}, f"Use one histogram, one bar, one line and one scatter chart (found: {sorted(kinds)}).")
CHECK_MESSAGE = "Four questions, four chart types, all labelled."
--- hints
- `axes[0, 1]` is the top-right panel.
- `ax.set(title=..., xlabel=..., ylabel=...)` labels a panel in one call.
- Monthly revenue: `orders.set_index("order_date")["revenue"].resample("MS").sum()`
