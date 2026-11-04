id: stats-r-2
stage: stats
lang: r
title: Proportions, confidence intervals and the bootstrap in R
--- task
For **Basic**-plan customers:

* **`p`** – churn rate, **`se`** – standard error `sqrt(p(1-p)/n)`
* **`ci_manual`** – `c(p - 1.96*se, p + 1.96*se)`
* **`pt`** – `prop.test(x = number churned, n = number of customers)`. Compare `pt$conf.int` with your interval.

Then bootstrap the **median income** of all customers: `set.seed(0)`, 2,000 resamples with
`replicate()` and `sample(..., replace = TRUE)`, and store the 95% interval in **`ci_median`**.
--- starter
df <- read.csv("data/customers.csv")
basic <- df$churned[df$plan == "Basic"]

p <- NA
se <- NA
ci_manual <- NA
pt <- NA
ci_median <- NA
--- solution
df <- read.csv("data/customers.csv")
basic <- df$churned[df$plan == "Basic"]

p <- mean(basic)
se <- sqrt(p * (1 - p) / length(basic))
ci_manual <- c(p - 1.96 * se, p + 1.96 * se)
pt <- prop.test(x = sum(basic), n = length(basic))
print(round(ci_manual, 3)); print(round(pt$conf.int, 3))

set.seed(0)
boots <- replicate(2000, median(sample(df$income, replace = TRUE)))
ci_median <- quantile(boots, c(0.025, 0.975))
print(ci_median)
--- check
d <- read.csv("data/customers.csv")
b <- d$churned[d$plan == "Basic"]
expect(abs(p - mean(b)) < 1e-12, "p should be the Basic churn rate.")
expect(abs(se - sqrt(mean(b) * (1 - mean(b)) / length(b))) < 1e-12, "se should be sqrt(p * (1 - p) / n).")
expect(length(ci_manual) == 2 && abs(ci_manual[1] - (p - 1.96 * se)) < 1e-12, "ci_manual should be p -/+ 1.96 * se.")
expect(inherits(pt, "htest") && abs(pt$estimate - p) < 1e-12, "pt should be prop.test(sum(basic), length(basic)).")
m <- median(d$income)
expect(length(ci_median) == 2 && ci_median[1] <= m && m <= ci_median[2] && diff(ci_median) > 1000,
       "ci_median should be the 2.5% and 97.5% quantiles of the bootstrap medians.")
--- hints
- `replicate(2000, median(sample(x, replace = TRUE)))`
- `quantile(boots, c(0.025, 0.975))`
