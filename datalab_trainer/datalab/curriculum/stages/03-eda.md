id: eda
title: Explore (EDA)
summary: Summaries, group comparisons, distributions, relationships and charts that answer questions.
--- lesson
# Module 3 · Exploratory Data Analysis

EDA is **asking the data questions** before you build anything. The business question for
Ridgeway is: *Which customers leave (churn), and what drives how much they spend?*
From now on use the clean table `data/customers.csv` (SQL view `customers`).

## 1. One variable at a time (univariate)

* **Numbers:** count, mean, median, standard deviation, min/max, quartiles, a histogram.
* **Categories:** counts and percentages, a bar chart.

```sql
SELECT plan, count(*) AS n, round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
FROM customers GROUP BY plan ORDER BY n DESC;

SELECT quantile_cont(income, [0.25, 0.5, 0.75]) AS quartiles, avg(income), stddev(income)
FROM customers;
```
```python
import pandas as pd
import matplotlib.pyplot as plt
df = pd.read_csv("data/customers.csv")
print(df.describe())
print(df["plan"].value_counts(normalize=True))
df["income"].plot.hist(bins=30, title="Income")
plt.show()
```
```r
df <- read.csv("data/customers.csv")
summary(df)
prop.table(table(df$plan))
hist(df$income, breaks = 30, main = "Income", xlab = "Income")
```

## 2. Compare groups (bivariate)

The most useful EDA question is usually *"how does the target differ between groups?"*
`churned` is 0/1, so **its mean is the churn rate**.

```sql
SELECT plan, round(avg(churned), 3) AS churn_rate, count(*) AS n
FROM customers GROUP BY plan ORDER BY churn_rate DESC;
```
```python
df.groupby("plan")["churned"].mean().sort_values(ascending=False)
df.boxplot(column="monthly_spend", by="plan")
plt.show()
```
```r
tapply(df$churned, df$plan, mean)
aggregate(churned ~ plan, data = df, FUN = mean)
boxplot(monthly_spend ~ plan, data = df)
```

## 3. Relationships between numbers

**Correlation** (−1 … +1) measures *linear* association. It doesn't show cause, and it
misses curved relationships, so **always plot it as well**.

```sql
SELECT corr(income, monthly_spend) AS r_income_spend,
       corr(tenure_months, churned) AS r_tenure_churn
FROM customers;
```
```python
num = df[["age", "income", "tenure_months", "support_calls", "monthly_spend", "churned"]]
print(num.corr().round(2))
df.plot.scatter(x="income", y="monthly_spend", alpha=0.4)
plt.show()
```
```r
num <- df[, c("age", "income", "tenure_months", "support_calls", "monthly_spend", "churned")]
round(cor(num), 2)
plot(df$income, df$monthly_spend, pch = 19, col = rgb(0, 0, 1, 0.3))
```

## 4. Time

Turn dates into periods (month, quarter) and look at trends and seasonality.

```sql
SELECT date_trunc('month', order_date) AS month,
       round(sum(quantity * unit_price * (1 - discount)), 2) AS revenue
FROM orders GROUP BY month ORDER BY month;
```
```python
orders = pd.read_csv("data/orders.csv", parse_dates=["order_date"])
orders["revenue"] = orders.quantity * orders.unit_price * (1 - orders.discount)
monthly = orders.set_index("order_date")["revenue"].resample("MS").sum()
monthly.plot(title="Monthly revenue"); plt.show()
```
```r
orders <- read.csv("data/orders.csv")
orders$revenue <- orders$quantity * orders$unit_price * (1 - orders$discount)
orders$month <- format(as.Date(orders$order_date), "%Y-%m")
monthly <- aggregate(revenue ~ month, data = orders, FUN = sum)
plot(seq_along(monthly$month), monthly$revenue, type = "l", xlab = "Month", ylab = "Revenue")
```

## Charts that communicate

* One message per chart, written as the **title** ("Basic-plan customers churn twice as often").
* Label axes with units. Start bar charts at zero.
* Histogram → distribution · Bar → compare categories · Line → change over time ·
  Scatter → relationship between two numbers · Box plot → distribution by group.

> **ggplot2 (R)**: `ggplot(df, aes(plan, monthly_spend)) + geom_boxplot()` —
> install with `install.packages("ggplot2")`. DataLab captures ggplot charts too
> (call `print(p)` on the plot object).

## Write down what you find

Write each finding as a sentence with a number in it. For example: *"Customers with 3+ support calls churn at
48% vs 14% for 0–1 calls."* These sentences become the Findings section of your report.
--- quiz
Q: `churned` is coded 1 for churned and 0 for stayed. What does `mean(churned)` give you?
- The number of churned customers
* The churn rate (share of customers who churned)
- Nothing meaningful
E: The mean of a 0/1 variable is the proportion of 1s.
Q: Correlation between income and spend is 0.75. What can you conclude?
- Higher income causes higher spend
* Income and spend have a strong positive linear association
- 75% of spend is explained by income
E: Correlation isn't causation. r² (0.56 here) is the share of variance explained, not r.
Q: Which chart best shows how monthly revenue changes over two years?
- Pie chart
- Histogram
* Line chart
- Box plot
E: Line charts show change over an ordered (time) axis.
Q: A correlation of 0 between two numbers means…
- They are unrelated in every way
* There is no linear relationship, but there could still be a curved one, so plot it
- One of them must be constant
E: A U-shaped relationship can have correlation close to 0. Always plot it.
