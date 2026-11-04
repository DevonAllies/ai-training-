id: forecast-py-3
stage: forecast
lang: python
title: Holt-Winters exponential smoothing
level: 2
--- task
Fit `statsmodels.tsa.holtwinters.ExponentialSmoothing` with **additive trend and additive seasonality**
(`seasonal_periods=52`) on the training weeks, forecast the 52 test weeks and compute **`mae_hw`**.

Then put all your results in one sorted **`leaderboard`** (a pandas Series of MAE, lowest first)
with at least: `naive`, `seasonal_growth`, `holt_winters`, `regression`.
--- starter
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

s = pd.read_csv("data/store_sales.csv", parse_dates=["week"])
train, test = s.iloc[:-52], s.iloc[-52:]

mae_hw = None
leaderboard = None
--- solution
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from sklearn.linear_model import LinearRegression

s = pd.read_csv("data/store_sales.csv", parse_dates=["week"])
train, test = s.iloc[:-52], s.iloc[-52:]
y, h = test["sales"].to_numpy(), train["sales"].to_numpy()

hw = ExponentialSmoothing(h, trend="add", seasonal="add", seasonal_periods=52).fit()
mae_hw = float(np.abs(y - hw.forecast(52)).mean())

s["t"] = np.arange(len(s))
w = s["week"].dt.isocalendar().week.astype(float)
s["sin1"], s["cos1"] = np.sin(2 * np.pi * w / 52), np.cos(2 * np.pi * w / 52)
X = ["t", "sin1", "cos1", "promo"]
reg = LinearRegression().fit(s.iloc[:-52][X], h)
mae_reg = float(np.abs(y - reg.predict(s.iloc[-52:][X])).mean())

growth = h[-52:].sum() / h[-104:-52].sum()
leaderboard = pd.Series({
    "naive": np.abs(y - h[-1]).mean(),
    "seasonal_growth": np.abs(y - h[-52:] * growth).mean(),
    "holt_winters": mae_hw,
    "regression": mae_reg,
}).sort_values()
print(leaderboard.round(0))
--- check
import pandas as pd
expect(mae_hw is not None and 3000 < mae_hw < 5000, f"mae_hw should be about 4,000; you have {mae_hw}. Use trend='add', seasonal='add', seasonal_periods=52.")
expect(isinstance(leaderboard, pd.Series) and {"naive", "seasonal_growth", "holt_winters", "regression"} <= set(leaderboard.index),
       "leaderboard should be a Series with naive, seasonal_growth, holt_winters and regression.")
expect(leaderboard.is_monotonic_increasing, "Sort the leaderboard, lowest MAE first.")
expect(leaderboard.index[0] == "regression", "Regression (with the promo calendar) should come out on top.")
--- hints
- `ExponentialSmoothing(values, trend="add", seasonal="add", seasonal_periods=52).fit().forecast(52)`
- `pd.Series({...}).sort_values()`
