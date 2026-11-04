id: explain-r-2
stage: explain
lang: r
title: Shape results in R (cross-tab, long format, segments)
--- task
* **`grid`** – churn rate matrix with regions as rows and plans as columns in the order
  `Basic, Standard, Premium`, rounded to 3 dp (`tapply(df$churned, list(df$region, df$plan), mean)`).
* **`long`** – a data frame with columns `region, plan, churn_rate` (12 rows), e.g. from
  `as.data.frame(as.table(grid))`.
* **`segments`** – a data frame with columns `band, customers, churn_rate` for support-call bands `0-1`, `2-3`, `4+`.
--- starter
df <- read.csv("data/customers.csv")

grid <- NA
long <- NA
segments <- NA
--- solution
df <- read.csv("data/customers.csv")

grid <- round(tapply(df$churned, list(df$region, df$plan), mean), 3)
grid <- grid[, c("Basic", "Standard", "Premium")]

long <- as.data.frame(as.table(grid), stringsAsFactors = FALSE)
names(long) <- c("region", "plan", "churn_rate")

band <- cut(df$support_calls, c(-1, 1, 3, 100), labels = c("0-1", "2-3", "4+"))
segments <- data.frame(band = levels(band),
                       customers = as.vector(table(band)),
                       churn_rate = round(as.vector(tapply(df$churned, band, mean)), 3))
print(grid); print(head(long)); print(segments)
--- check
ref <- read.csv("data/customers.csv")
g <- tapply(ref$churned, list(ref$region, ref$plan), mean)
expect(is.matrix(grid) && identical(colnames(grid), c("Basic", "Standard", "Premium")), "grid columns should be Basic, Standard, Premium.")
expect(all(abs(grid - g[rownames(grid), colnames(grid)]) < 0.0006), "grid values should be churn rates rounded to 3 dp.")
expect(is.data.frame(long) && nrow(long) == 12 && all(c("region", "plan", "churn_rate") %in% names(long)), "long should have 12 rows: region, plan, churn_rate.")
expect(is.data.frame(segments) && nrow(segments) == 3 && sum(segments$customers) == 600, "segments should have 3 bands covering all 600 customers.")
--- hints
- `tapply(values, list(rows, cols), mean)` gives a matrix.
- `as.data.frame(as.table(m))` turns a matrix into long format.
