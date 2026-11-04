id: forecast-py-2
stage: forecast
lang: python
title: Forecast with regression - trend, seasonality and promotions
--- task
Add time features to `s`:

* `t` – a trend counter 0, 1, 2, …
* `sin1`, `cos1` – Fourier terms from the ISO week number `w`: `sin(2πw/52)`, `cos(2πw/52)`
* `promo` is already in the data (known in advance, so it's allowed)

Fit `LinearRegression` on the training weeks (all but the last 52) with `t, sin1, cos1, promo`, predict the
test weeks and compute **`mae_reg`**. Also compute a rough 95% **prediction band** `pred ± 1.96 × sd(training residuals)`
and store the share of test weeks inside it in **`coverage`**.

Plot actual vs forecast with the band shaded (`ax.fill_between`).
--- starter
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression

s = pd.read_csv("data/store_sales.csv", parse_dates=["week"])

mae_reg = None
coverage = None
--- solution
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression

s = pd.read_csv("data/store_sales.csv", parse_dates=["week"])
s["t"] = np.arange(len(s))
w = s["week"].dt.isocalendar().week.astype(float)
s["sin1"] = np.sin(2 * np.pi * w / 52)
s["cos1"] = np.cos(2 * np.pi * w / 52)
X = ["t", "sin1", "cos1", "promo"]
train, test = s.iloc[:-52], s.iloc[-52:]

reg = LinearRegression().fit(train[X], train["sales"])
pred = reg.predict(test[X])
mae_reg = float(np.abs(test["sales"] - pred).mean())
sd = float(np.std(train["sales"] - reg.predict(train[X]), ddof=len(X) + 1))
lo, hi = pred - 1.96 * sd, pred + 1.96 * sd
coverage = float(((test["sales"] >= lo) & (test["sales"] <= hi)).mean())
print({k: round(float(v), 1) for k, v in zip(X, reg.coef_)}, f"MAE {mae_reg:,.0f}, coverage {coverage:.0%}")

fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(train["week"], train["sales"], color="#999999", label="history")
ax.plot(test["week"], test["sales"], color="black", label="actual")
ax.plot(test["week"], pred, color="#d1495b", label="forecast")
ax.fill_between(test["week"], lo, hi, color="#d1495b", alpha=0.15, label="95% band")
ax.set(title=f"Regression forecast for 2024: MAE {mae_reg:,.0f}", ylabel="Weekly sales")
ax.legend(loc="upper left")
plt.show()
--- check
import numpy as np
expect(all(c in s.columns for c in ["t", "sin1", "cos1"]), "Add the columns t, sin1 and cos1 to s.")
expect(mae_reg is not None and 2000 < mae_reg < 3300, f"mae_reg should be about 2,700 (trend + seasonality + promo); you have {mae_reg}.")
expect(coverage is not None and 0.8 <= coverage <= 1.0, "coverage should be the share of test weeks inside pred +/- 1.96 x sd (most of them).")
CHECK_MESSAGE = f"MAE {mae_reg:,.0f}, about a third lower than the best baseline, because the model knows the promotion calendar."
--- hints
- `w = s["week"].dt.isocalendar().week.astype(float)`
- `reg.predict(test[X])`
- `ax.fill_between(x, lower, upper, alpha=0.15)`
