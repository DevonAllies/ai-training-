id: visualise-r-1
stage: visualise
lang: r
title: Small multiples in base R
--- task
Draw a **2 × 2 grid** of charts with `par(mfrow = c(2, 2))`:

1. histogram of `monthly_spend`
2. bar chart of churn rate by plan, sorted (store the rates in **`rates`**)
3. line chart of monthly revenue (store it in a data frame **`monthly`** with columns `month`, `revenue`)
4. scatter plot of income vs monthly spend

Give every chart a title (`main =`) and axis labels (`xlab =`, `ylab =`).
--- starter
df <- read.csv("data/customers.csv")
orders <- read.csv("data/orders.csv")
orders$revenue <- orders$quantity * orders$unit_price * (1 - orders$discount)

rates <- NA
monthly <- NA

par(mfrow = c(2, 2))
# four plots here
--- solution
df <- read.csv("data/customers.csv")
orders <- read.csv("data/orders.csv")
orders$revenue <- orders$quantity * orders$unit_price * (1 - orders$discount)

rates <- sort(tapply(df$churned, df$plan, mean) * 100, decreasing = TRUE)
orders$month <- format(as.Date(orders$order_date), "%Y-%m")
monthly <- aggregate(revenue ~ month, data = orders, FUN = sum)

par(mfrow = c(2, 2), mar = c(4, 4, 3, 1))
hist(df$monthly_spend, breaks = 30, col = "steelblue", border = "white",
     main = "Half of customers spend 58-86", xlab = "Monthly spend", ylab = "Customers")
barplot(rates, col = "steelblue", border = NA, main = "Basic customers churn most",
        xlab = "Plan", ylab = "Churn rate (%)")
plot(seq_len(nrow(monthly)), monthly$revenue, type = "l", col = "steelblue", lwd = 2,
     main = "Revenue has grown every year", xlab = "Month number", ylab = "Revenue")
plot(df$income, df$monthly_spend, pch = 19, cex = 0.5, col = rgb(0.27, 0.51, 0.71, 0.4),
     main = "Spend rises with income", xlab = "Income", ylab = "Monthly spend")
par(mfrow = c(1, 1))
--- check
expect(dev.cur() > 1, "Draw the charts (no plot was made).")
expect(is.numeric(rates) && length(rates) == 3 && !is.unsorted(rev(rates)), "rates should be churn rate by plan, sorted from high to low.")
expect(is.data.frame(monthly) && all(c("month", "revenue") %in% names(monthly)) && nrow(monthly) == 48,
       "monthly should have one row per month (48) with columns month and revenue.")
o <- read.csv("data/orders.csv")
expect(abs(sum(monthly$revenue) - sum(o$quantity * o$unit_price * (1 - o$discount))) < 0.01, "monthly$revenue should add up to total revenue.")
--- hints
- `format(as.Date(x), "%Y-%m")` gives the month.
- `aggregate(revenue ~ month, data = orders, FUN = sum)`
- `plot(x, y, type = "l")` draws a line.
