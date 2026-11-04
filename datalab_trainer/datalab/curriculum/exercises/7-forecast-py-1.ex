id: forecast-py-1
stage: forecast
lang: python
title: Time-based split and baseline forecasts
--- task
Load `data/store_sales.csv` (parse `week` as a date). Use the **last 52 weeks** as the test set:
`train, test = s.iloc[:-52], s.iloc[-52:]`.

Build a dictionary **`mae`** with the test-set MAE of four baselines:

* `"naive"` – every test week = last training value
* `"mean"` – every test week = mean of the last 52 training weeks
* `"seasonal"` – each test week = the same week a year earlier (the last 52 training values, in order)
* `"seasonal_growth"` – seasonal × (sum of last 52 training weeks / sum of the 52 before)

Plot the test actuals and the best baseline.
--- starter
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

s = pd.read_csv("data/store_sales.csv", parse_dates=["week"])
train, test = s.iloc[:-52], s.iloc[-52:]
y = test["sales"].to_numpy()

mae = {}
--- solution
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

s = pd.read_csv("data/store_sales.csv", parse_dates=["week"])
train, test = s.iloc[:-52], s.iloc[-52:]
y = test["sales"].to_numpy()
hist = train["sales"].to_numpy()

growth = hist[-52:].sum() / hist[-104:-52].sum()
forecasts = {
    "naive": np.full(52, hist[-1]),
    "mean": np.full(52, hist[-52:].mean()),
    "seasonal": hist[-52:],
    "seasonal_growth": hist[-52:] * growth,
}
mae = {k: float(np.abs(y - f).mean()) for k, f in forecasts.items()}
for k, v in sorted(mae.items(), key=lambda kv: kv[1]):
    print(f"{k:16s} MAE {v:8,.0f}")

best = min(mae, key=mae.get)
fig, ax = plt.subplots(figsize=(9, 4))
ax.plot(test["week"], y, color="black", label="actual")
ax.plot(test["week"], forecasts[best], color="#d1495b", label=best)
ax.set(title=f"Best baseline: {best} (MAE {mae[best]:,.0f})", ylabel="Weekly sales")
ax.legend()
plt.show()
--- check
import numpy as np
import pandas as pd
d = pd.read_csv("data/store_sales.csv")
h, t = d["sales"].to_numpy()[:-52], d["sales"].to_numpy()[-52:]
g = h[-52:].sum() / h[-104:-52].sum()
ref = {"naive": np.abs(t - h[-1]).mean(), "mean": np.abs(t - h[-52:].mean()).mean(),
       "seasonal": np.abs(t - h[-52:]).mean(), "seasonal_growth": np.abs(t - g * h[-52:]).mean()}
expect(isinstance(mae, dict) and set(mae) == set(ref), f"mae should have the keys {sorted(ref)}.")
for k, v in ref.items():
    expect(abs(mae[k] - v) < 0.5, f"mae['{k}'] should be about {v:,.0f}; you have {mae[k]:,.0f}.")
CHECK_MESSAGE = "Seasonal naive alone ignores growth; scaling it by last year's growth halves the error."
--- hints
- `np.full(52, value)` repeats one value 52 times.
- The last 52 training values are `train["sales"].to_numpy()[-52:]`, which is the same weeks one year before the test weeks.
- MAE: `np.abs(y - forecast).mean()`
