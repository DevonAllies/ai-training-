id: visualise-py-2
stage: visualise
lang: python
title: Declutter and label a report chart
--- task
Turn a default chart into a report-quality one. Make a bar chart of **churn rate (%) by plan** with
`fig, ax = plt.subplots()` and:

* bars **sorted** from highest to lowest,
* **values labelled** on the bars (`ax.bar_label`),
* the **top and right borders removed** (`ax.spines[["top", "right"]].set_visible(False)`),
* a **title that states the message**, a y-axis label with the unit, and the y-axis **starting at 0**,
* the highest bar in an **accent colour** and the others grey.

Keep `fig` and `ax`.
--- starter
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/customers.csv")
rates = df.groupby("plan")["churned"].mean() * 100

fig, ax = plt.subplots(figsize=(6, 3.5))
ax.bar(rates.index, rates.values)
plt.show()
--- solution
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/customers.csv")
rates = (df.groupby("plan")["churned"].mean() * 100).sort_values(ascending=False)

fig, ax = plt.subplots(figsize=(6, 3.5))
colors = ["#d1495b"] + ["#bbbbbb"] * (len(rates) - 1)
bars = ax.bar(rates.index, rates.values, color=colors)
ax.bar_label(bars, fmt="%.0f%%", padding=3)
ax.spines[["top", "right"]].set_visible(False)
ax.set(title="Basic customers churn almost 3x as often as Premium",
       ylabel="Churn rate (%)", ylim=(0, rates.max() * 1.2))
plt.show()
--- check
expect("ax" in dir() and hasattr(ax, "patches"), "Keep the axes in a variable called ax.")
heights = [p.get_height() for p in ax.patches]
expect(len(heights) == 3, "Draw one bar per plan.")
expect(heights == sorted(heights, reverse=True), "Sort the bars from highest to lowest.")
expect(len(ax.texts) >= 3, "Label each bar with its value (ax.bar_label).")
expect(not ax.spines["top"].get_visible() and not ax.spines["right"].get_visible(), "Remove the top and right borders.")
t = ax.get_title().strip()
expect(len(t.split()) >= 4 and t.lower() not in ("churn by plan", "churn rate by plan"), "Write a title that states the message (4+ words).")
expect(ax.get_ylabel().strip() != "", "Label the y-axis, including the unit.")
expect(abs(ax.get_ylim()[0]) < 1e-9, "Start the y-axis at 0.")
cols = [tuple(p.get_facecolor()) for p in ax.patches]
expect(cols[0] != cols[1] and cols[1] == cols[2], "Give the highest bar an accent colour and the others one shared colour.")
CHECK_MESSAGE = "That's a chart a manager understands in five seconds."
--- hints
- `rates.sort_values(ascending=False)` before plotting.
- `bars = ax.bar(...)`, then `ax.bar_label(bars, fmt="%.0f%%")`.
- Colours: `color=["#d1495b", "#bbbbbb", "#bbbbbb"]`.
