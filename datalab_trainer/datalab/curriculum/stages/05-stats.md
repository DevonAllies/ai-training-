id: stats
title: Statistics & testing
summary: Sampling, confidence intervals, hypothesis tests and how to tell a real difference from noise.
--- lesson
# Module 5 · Statistics & hypothesis testing

In Module 3 you saw that churn is 27% in the East but 20% in the North. **Is that a real difference,
or just luck in who happened to be in the data?** Statistics gives you a way to answer that.

## Samples, uncertainty and the standard error

Your 600 customers are a **sample**. A different sample would give slightly different numbers.
The **standard error (SE)** measures how much an estimate would wobble between samples:

| Estimate | Standard error |
|---|---|
| a mean | `sd / sqrt(n)` |
| a proportion `p` | `sqrt(p × (1 − p) / n)` |

Bigger samples → smaller SE → more precise estimates. Precision grows with **√n**: four times the data halves the SE.

## Confidence intervals

A **95% confidence interval** is roughly `estimate ± 1.96 × SE`. If you repeated the study many
times, 95% of intervals built this way would contain the true value. Report intervals, not just
point estimates: *"Basic churn is 31% (95% CI 25%–36%)."*

```sql
SELECT plan, count(*) AS n, avg(churned) AS p,
       sqrt(avg(churned) * (1 - avg(churned)) / count(*)) AS se,
       avg(churned) - 1.96 * se AS lower_95, avg(churned) + 1.96 * se AS upper_95
FROM customers GROUP BY plan;
```
```python
import numpy as np
p = df.loc[df.plan == "Basic", "churned"].mean()
n = (df.plan == "Basic").sum()
se = np.sqrt(p * (1 - p) / n)
print(p - 1.96 * se, p + 1.96 * se)
```
```r
basic <- df$churned[df$plan == "Basic"]
p <- mean(basic); se <- sqrt(p * (1 - p) / length(basic))
c(p - 1.96 * se, p + 1.96 * se)
prop.test(sum(basic), length(basic))$conf.int     # exact-ish interval from R
```

## Hypothesis tests in five steps

1. **Null hypothesis H₀**: "there is no difference" (e.g. churn is the same in every region).
2. **Alternative H₁**: "there is a difference".
3. Choose a **test** that fits the data (table below) and a **significance level**, usually α = 0.05.
4. Compute the **p-value**: *if H₀ were true*, how likely is a difference at least this big?
5. **p < α → reject H₀** ("statistically significant"). Otherwise you **don't have enough evidence**.
   That isn't the same as proving there's no difference.

| Question | Data | Test | Python (`scipy.stats`) | R |
|---|---|---|---|---|
| Do two groups have different means? | number × 2 groups | Welch **t-test** | `ttest_ind(a, b, equal_var=False)` | `t.test(y ~ group)` |
| Is a category related to an outcome? | 2 categorical | **chi-square** | `chi2_contingency(table)` | `chisq.test(table)` |
| Do two proportions differ? | 0/1 × 2 groups | **two-proportion z-test** | by hand or `statsmodels` | `prop.test()` |
| Are two numbers correlated? | 2 numbers | Pearson / Spearman | `pearsonr`, `spearmanr` | `cor.test()` |
| Means of 3+ groups? | number × k groups | ANOVA | `f_oneway` | `aov()` |

## What the Ridgeway data says

```python
from scipy import stats
import pandas as pd
stats.chi2_contingency(pd.crosstab(df.region, df.churned))   # p ≈ 0.47 -> no evidence regions differ
stats.chi2_contingency(pd.crosstab(df.plan, df.churned))     # p ≈ 0.00002 -> plans really differ
stats.ttest_ind(df.tenure_months[df.churned == 1],
                df.tenure_months[df.churned == 0], equal_var=False)   # churners have much shorter tenure
```
```r
chisq.test(table(df$region, df$churned))$p.value    # ~0.47
chisq.test(table(df$plan, df$churned))$p.value      # ~0.00002
t.test(tenure_months ~ churned, data = df)
```

The 7-point gap between regions **looks** large but is well within what chance produces with
~150 customers per region. Don't build a regional retention campaign on it.

## Bootstrap: confidence intervals for anything

When there's no simple formula (a median, a ratio, an AUC), **resample the data with replacement**
thousands of times, recompute the statistic each time, and take the 2.5th and 97.5th percentiles.

```python
rng = np.random.default_rng(0)
x = df["income"].to_numpy()
boots = [np.median(rng.choice(x, size=len(x), replace=True)) for _ in range(2000)]
np.percentile(boots, [2.5, 97.5])
```
```r
set.seed(0)
boots <- replicate(2000, median(sample(df$income, replace = TRUE)))
quantile(boots, c(0.025, 0.975))
```

## Traps

* **Statistical ≠ practical significance.** With a million rows, a 0.1% difference is "significant" but may not matter. Always report the **effect size** (the difference itself, with its CI).
* **Multiple testing.** Test 20 random things at α = 0.05 and you expect one false "discovery". Decide your questions up front, or adjust (Bonferroni: α / number of tests).
* **p-hacking.** Don't keep slicing the data until something is significant.
* **Correlation ≠ causation**, still. An A/B test (randomised experiment) is the way to show cause.
--- quiz
Q: Churn is 27% in the East and 20% in the North; a chi-square test gives p = 0.47. What do you conclude?
- East customers definitely churn more
* There is no good evidence that churn differs by region; the gap could easily be chance
- The test proves regions have identical churn
E: A large p-value means the data are consistent with no difference. It doesn't prove there is none.
Q: What happens to the standard error if you collect 4 times as much data?
- It stays the same
* It halves
- It quarters
E: SE shrinks with the square root of n: sqrt(4) = 2.
Q: Which test checks whether average monthly spend differs between churners and stayers?
* A two-sample (Welch) t-test
- A chi-square test
- A correlation test
E: A t-test compares means of a numeric variable between two groups.
Q: A p-value of 0.03 means…
- There is a 3% chance the null hypothesis is true
* If there were no real difference, a result this extreme would happen about 3% of the time
- The effect is 3% large
E: The p-value is computed assuming H0 is true. It isn't the probability that H0 is true.
Q: You test 20 product categories for a difference and one gives p = 0.04. Best reaction?
- Launch a campaign for that category
* Be cautious: with 20 tests, one p < 0.05 is expected by chance alone
E: That's the multiple-testing problem. Adjust α (e.g. 0.05/20) or confirm on new data.
