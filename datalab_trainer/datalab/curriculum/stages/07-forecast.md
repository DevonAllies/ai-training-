id: forecast
title: Forecast
summary: Time-series basics: trend and seasonality, honest time-based evaluation, baselines, Holt-Winters and regression forecasts.
--- lesson
# Module 7 · Time-series forecasting

Ridgeway's finance team asks: **"What will weekly sales be over the next year?"** That's a
**forecasting** question. Here the order of the rows matters, and the future has to be predicted from the past only.

Data: `data/store_sales.csv`, weekly sales from Jan 2021 to Dec 2024 (209 weeks), with a `promo`
flag for weeks with a promotion. (SQL view: `store_sales`.)

## 1. Look at the series: trend, seasonality, noise

Most business series are a mix of:

* **Trend**: the long-run direction (Ridgeway grows every year).
* **Seasonality**: a pattern that repeats every period (a December peak, every 52 weeks).
* **Events**: promotions, holidays, outages.
* **Noise**: what's left.

```python
import pandas as pd
import matplotlib.pyplot as plt
s = pd.read_csv("data/store_sales.csv", parse_dates=["week"])
s.plot(x="week", y="sales"); plt.show()
s["ma13"] = s["sales"].rolling(13, center=True).mean()     # a moving average smooths noise
```
```r
s <- read.csv("data/store_sales.csv")
y <- ts(s$sales, frequency = 52, start = c(2021, 1))
plot(decompose(y))            # trend, seasonal and random parts
```
```sql
SELECT week, sales,
       avg(sales) OVER (ORDER BY week ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS ma4,
       lag(sales, 52) OVER (ORDER BY week)                                   AS same_week_last_year
FROM store_sales ORDER BY week;
```

## 2. Evaluate honestly: split by time

Never split a time series randomly. That lets the model "see the future". Instead hold out the **most
recent period** as the test set and forecast all of it from the training data only:

```
train: first 157 weeks (2021-01 .. 2024-01-01)     test: last 52 weeks (2024-01-08 .. 2024-12-30)
```

Measure error with **MAE** (average absolute error, in sales units) or **MAPE** (average % error).

## 3. Always start with baselines

| Baseline | Forecast for every test week | MAE here |
|---|---|---|
| naive | the last training value | ~6,400 |
| mean | average of the last 52 training weeks | ~9,000 |
| seasonal naive | the same week one year earlier | ~8,700 |
| seasonal naive × growth | same week last year × last year's growth rate | ~4,100 |

A model is only worth using if it beats these. Note how seasonal naive alone does *badly* here: it
ignores the growth trend.

## 4. Exponential smoothing (Holt-Winters)

Holt-Winters keeps a smoothed **level**, **trend** and **seasonal** component and projects them forward.

```python
from statsmodels.tsa.holtwinters import ExponentialSmoothing
train, test = s.iloc[:-52], s.iloc[-52:]
hw = ExponentialSmoothing(train["sales"], trend="add", seasonal="add", seasonal_periods=52).fit()
forecast = hw.forecast(52)
```
```r
train <- ts(head(s$sales, -52), frequency = 52, start = c(2021, 1))
hw <- HoltWinters(train)              # base R, no packages needed
fc <- predict(hw, n.ahead = 52)
```

## 5. Regression with time features

A linear regression can forecast too, if you give it **features of time**:

* a **trend** counter `t = 0, 1, 2, …`
* **seasonal** terms: `sin(2π·week/52)` and `cos(2π·week/52)` (*Fourier terms*) or month dummies
* **known future events**: `promo` (planned in advance, so it's legitimate to use)

```python
import numpy as np
from sklearn.linear_model import LinearRegression
s["t"] = np.arange(len(s))
w = s["week"].dt.isocalendar().week.astype(float)
s["sin1"], s["cos1"] = np.sin(2 * np.pi * w / 52), np.cos(2 * np.pi * w / 52)
X = ["t", "sin1", "cos1", "promo"]
train, test = s.iloc[:-52], s.iloc[-52:]
reg = LinearRegression().fit(train[X], train["sales"])
pred = reg.predict(test[X])           # MAE ~2,700: best here, because it knows about promotions
```
```r
s$t <- seq_len(nrow(s)) - 1
w <- as.numeric(strftime(as.Date(s$week), "%V"))
s$sin1 <- sin(2 * pi * w / 52); s$cos1 <- cos(2 * pi * w / 52)
fit <- lm(sales ~ t + sin1 + cos1 + promo, data = head(s, -52))
pred <- predict(fit, newdata = tail(s, 52))
```

## 6. Communicate uncertainty

A forecast is a range, not a number. Give a **prediction interval** (e.g. ±1.96 × the standard
deviation of the test errors for a rough 95% band) and plot it as a shaded area. Say which
assumptions it depends on (promotion plan, no new competitor…).

> **More tools**: ARIMA (`statsmodels.tsa.arima.model.ARIMA`, R `arima()`), Prophet, and the R
> `forecast` / `fable` packages (`auto.arima()`, `ets()`), plus cross-validation over several
> forecast origins ("rolling origin").
--- quiz
Q: Why must time-series test sets be the most recent period instead of random rows?
- Random sampling is slower
* A random split lets the model learn from the future, so the test error looks better than it will be
- Libraries require it
E: Real forecasts only ever have the past available. The evaluation must copy that.
Q: The seasonal naive forecast (same week last year) does worse than the plain naive forecast here. Why?
* Sales grow every year, and seasonal naive ignores that trend
- There is no seasonality
- The data has missing weeks
E: Multiplying last year by the growth rate fixes most of it, which shows the problem was the trend.
Q: Which feature can you legitimately use in a forecast for next year?
- Next year's actual sales
* The planned promotion calendar
- The test-set average
E: Only information known at forecast time is allowed. Promotions are planned in advance.
Q: What does a 13-week centred moving average mostly remove?
- The trend
* Short-term noise (and some seasonality)
- Nothing
E: Averaging nearby weeks smooths noise and leaves the slower trend.
