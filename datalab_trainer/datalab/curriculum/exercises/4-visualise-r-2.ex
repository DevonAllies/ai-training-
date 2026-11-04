id: visualise-r-2
stage: visualise
lang: r
title: A labelled, decluttered bar chart in R
--- task
Make a report-quality bar chart of **churn rate (%) by plan**:

* **`rates`** sorted from highest to lowest,
* **`bp <- barplot(...)`** (barplot returns the bar positions), with `border = NA`, the first bar in an
  accent colour and the others grey, `ylim` from 0 to a little above the maximum,
* the values written on top of the bars with `text(bp, rates, labels = ..., pos = 3)`,
* a title stating the message and a y-axis label with the unit.
--- starter
df <- read.csv("data/customers.csv")
rates <- tapply(df$churned, df$plan, mean) * 100
barplot(rates)
--- solution
df <- read.csv("data/customers.csv")
rates <- sort(tapply(df$churned, df$plan, mean) * 100, decreasing = TRUE)
bp <- barplot(rates, col = c("#d1495b", "grey75", "grey75"), border = NA,
              ylim = c(0, max(rates) * 1.2), las = 1,
              main = "Basic customers churn almost 3x as often as Premium",
              ylab = "Churn rate (%)")
text(bp, rates, labels = sprintf("%.0f%%", rates), pos = 3)
--- check
expect(dev.cur() > 1, "Draw the chart.")
expect(is.numeric(rates) && length(rates) == 3 && !is.unsorted(rev(rates)), "Sort rates from high to low before plotting.")
expect(exists("bp") && is.numeric(bp) && length(bp) == 3, "Keep the result of barplot() in bp (it holds the bar positions for text()).")
expect(abs(max(rates) - 100 * max(tapply(read.csv("data/customers.csv")$churned, read.csv("data/customers.csv")$plan, mean))) < 1e-9,
       "rates should be churn rate in percent (x 100).")
--- hints
- `sort(x, decreasing = TRUE)`
- `bp <- barplot(...)` then `text(bp, rates, labels = sprintf("%.0f%%", rates), pos = 3)`
