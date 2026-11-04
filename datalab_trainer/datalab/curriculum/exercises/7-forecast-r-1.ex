id: forecast-r-1
stage: forecast
lang: r
title: ts objects, decomposition and baselines in R
--- task
1. Make **`y`**, a `ts` of the sales with `frequency = 52, start = c(2021, 1)`, and **`dec <- decompose(y)`**. Plot it.
2. Split: **`train`** = all but the last 52 values, **`test`** = the last 52 (`head(x, -52)`, `tail(x, 52)`).
3. **`mae_naive`** – forecast every test week with the last training value.
4. **`mae_seasonal_growth`** – last 52 training values × growth (sum of last 52 / sum of the 52 before).
--- starter
s <- read.csv("data/store_sales.csv")

y <- NA
dec <- NA
mae_naive <- NA
mae_seasonal_growth <- NA
--- solution
s <- read.csv("data/store_sales.csv")

y <- ts(s$sales, frequency = 52, start = c(2021, 1))
dec <- decompose(y)
plot(dec)

train <- head(s$sales, -52)
test <- tail(s$sales, 52)
n <- length(train)
mae_naive <- mean(abs(test - train[n]))
growth <- sum(train[(n - 51):n]) / sum(train[(n - 103):(n - 52)])
mae_seasonal_growth <- mean(abs(test - growth * train[(n - 51):n]))
cat("naive MAE:", round(mae_naive), " seasonal x growth MAE:", round(mae_seasonal_growth), "\n")
--- check
expect(is.ts(y) && frequency(y) == 52 && length(y) == 209, "y should be ts(sales, frequency = 52, start = c(2021, 1)).")
expect(inherits(dec, "decomposed.ts"), "dec should be decompose(y).")
d <- read.csv("data/store_sales.csv")$sales
h <- head(d, -52); t <- tail(d, 52); n <- length(h)
expect(abs(mae_naive - mean(abs(t - h[n]))) < 0.5, "mae_naive should use the last training value for every test week.")
g <- sum(h[(n - 51):n]) / sum(h[(n - 103):(n - 52)])
expect(abs(mae_seasonal_growth - mean(abs(t - g * h[(n - 51):n]))) < 0.5, "mae_seasonal_growth is wrong. Check the growth factor and the last 52 training values.")
--- hints
- `head(x, -52)` drops the last 52; `tail(x, 52)` keeps them.
- `train[(n - 51):n]` is the last 52 training values.
