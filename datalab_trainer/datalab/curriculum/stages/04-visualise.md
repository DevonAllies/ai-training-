id: visualise
title: Visualise
summary: Choose the right chart, prepare the data for it, and design charts that make one point clearly.
--- lesson
# Module 4 · Data visualisation

Module 3 used charts to **explore**. This module is about charts that **explain**: the ones that go in
a report or a slide, where a busy reader has to get the point in five seconds.

## 1. Pick the chart from the question

| The question is about… | Use | Avoid |
|---|---|---|
| comparing categories | **bar chart** (horizontal if labels are long), sorted | pie charts with more than 3 slices |
| change over time | **line chart** | bars for long series |
| distribution of one number | **histogram** or box plot | a bar per individual value |
| relationship between two numbers | **scatter plot** (+ trend line) | dual-axis charts |
| parts of a whole over time | stacked bars of **percentages** | 3-D anything |
| a grid of two categories | **heatmap** / table with colour | |

## 2. Prepare the data first

Charts work best on data that is already in shape: aggregated, sorted, and in **long** format
(one row per bar or point). That work is often easiest in SQL:

```sql
-- histogram bins: one row per bar
SELECT floor(monthly_spend / 10) * 10 AS bin_start, count(*) AS customers
FROM customers GROUP BY bin_start ORDER BY bin_start;
```
```python
rates = df.groupby("plan")["churned"].mean().sort_values()        # sorted for a bar chart
monthly = orders.set_index("order_date")["revenue"].resample("MS").sum()
```
```r
rates <- sort(tapply(df$churned, df$plan, mean))
```

## 3. Design: remove everything that isn't data

1. **Title = the message.** "Basic customers churn almost 3× as often", not "Churn by plan".
2. **Sort** bars by value, unless the categories have a natural order (months, bands).
3. **Label directly** (value on the bar, name at the end of a line) instead of a legend where you can.
4. **Remove clutter**: top/right borders, heavy grid lines, decimals nobody needs.
5. **Start bar axes at zero.** Line charts may zoom in, but say so.
6. **Use colour on purpose**: grey for context, one accent colour for the thing you want noticed.
   Avoid red/green as the only difference (about 1 in 12 men is colour-blind).
7. **Units** on axes, and a **source** line under report charts.

## A decluttered, labelled bar chart

```python
import matplotlib.pyplot as plt
rates = df.groupby("plan")["churned"].mean().sort_values(ascending=False) * 100
fig, ax = plt.subplots(figsize=(6, 3.5))
bars = ax.bar(rates.index, rates.values, color=["#d1495b", "#bbbbbb", "#bbbbbb"])
ax.bar_label(bars, fmt="%.0f%%", padding=3)
ax.spines[["top", "right"]].set_visible(False)
ax.set(title="Basic customers churn almost 3x as often", ylabel="Churn rate (%)", ylim=(0, 40))
plt.show()
```
```r
rates <- sort(tapply(df$churned, df$plan, mean) * 100, decreasing = TRUE)
bp <- barplot(rates, col = c("#d1495b", "grey75", "grey75"), border = NA, ylim = c(0, 40),
              main = "Basic customers churn almost 3x as often", ylab = "Churn rate (%)")
text(bp, rates, labels = sprintf("%.0f%%", rates), pos = 3)
```

## Small multiples

Several small charts with **the same axes** are easier to compare than one crowded chart.

```python
fig, axes = plt.subplots(2, 2, figsize=(10, 7))
axes[0, 0].hist(df["monthly_spend"], bins=30)
axes[0, 1].bar(rates.index, rates.values)
axes[1, 0].plot(monthly.index, monthly.values)
axes[1, 1].scatter(df["income"], df["monthly_spend"], s=8, alpha=0.4)
fig.tight_layout()
plt.show()
```
```r
par(mfrow = c(2, 2))            # 2 x 2 grid of plots
hist(df$monthly_spend); barplot(rates); plot(monthly, type = "l"); plot(df$income, df$monthly_spend)
par(mfrow = c(1, 1))
```

## Other libraries you'll meet

* **seaborn** (Python): statistical charts in one line, e.g. `sns.boxplot(data=df, x="plan", y="monthly_spend")`.
* **plotly** (Python/R): interactive charts for dashboards.
* **ggplot2** (R): a "grammar of graphics", `ggplot(df, aes(plan, monthly_spend)) + geom_boxplot() + theme_minimal()`.
* BI tools (Power BI, Tableau, Looker) take SQL-shaped tables, so module 4's SQL skills carry straight over.
--- quiz
Q: Which chart is best for comparing churn rate across 3 plans?
- Pie chart
* A bar chart sorted by churn rate
- Line chart
- Scatter plot
E: Bars compare categories. Sorting makes the ranking obvious.
Q: What is the best title for a churn-by-plan chart?
- Churn by plan
- Figure 1
* Basic customers churn almost 3x as often as Premium
E: A title that states the message tells the reader what to see.
Q: Why should a bar chart's value axis start at zero?
* Bar length encodes the value, so a cut axis exaggerates differences
- matplotlib requires it
- It makes the chart smaller
E: Line charts can zoom in on a range; bars can't without misleading the reader.
Q: You want to show a 4-year monthly revenue trend. Which chart?
- Histogram
* Line chart
- Pie chart
E: Lines show change over an ordered time axis.
