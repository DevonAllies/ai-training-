id: stats-r-1
stage: stats
lang: r
title: t.test and chisq.test in R
--- task
* **`tt`** – Welch t-test of `tenure_months` between churners and stayers: `t.test(tenure_months ~ churned, data = df)`
* **`ct_plan`** – `chisq.test(table(df$plan, df$churned))`
* **`ct_region`** – the same for region
* **`significant`** – a named logical vector `c(tenure = ..., plan = ..., region = ...)` at α = 0.05

Print the tests and read the output: where is the p-value? The confidence interval?
--- starter
df <- read.csv("data/customers.csv")

tt <- NA
ct_plan <- NA
ct_region <- NA
significant <- NA
--- solution
df <- read.csv("data/customers.csv")

tt <- t.test(tenure_months ~ churned, data = df)
ct_plan <- chisq.test(table(df$plan, df$churned))
ct_region <- chisq.test(table(df$region, df$churned))
significant <- c(tenure = tt$p.value < 0.05,
                 plan = ct_plan$p.value < 0.05,
                 region = ct_region$p.value < 0.05)
print(tt); print(ct_plan); print(ct_region); print(significant)
--- check
expect(inherits(tt, "htest") && grepl("t-test", tt$method), "tt should be the result of t.test().")
expect(inherits(ct_plan, "htest") && inherits(ct_region, "htest"), "ct_plan and ct_region should be chisq.test() results.")
d <- read.csv("data/customers.csv")
expect(abs(ct_region$p.value - chisq.test(table(d$region, d$churned))$p.value) < 1e-9, "ct_region should test region against churned.")
expect(is.logical(significant) && identical(unname(significant[c("tenure", "plan", "region")]), c(TRUE, TRUE, FALSE)),
       "significant should be c(tenure = TRUE, plan = TRUE, region = FALSE).")
CHECK_MESSAGE <- "Tenure and plan are clearly related to churn; region isn't (p ~ 0.47)."
--- hints
- `t.test(y ~ group, data = df)` uses Welch's test by default.
- Every test result has `$p.value`.
