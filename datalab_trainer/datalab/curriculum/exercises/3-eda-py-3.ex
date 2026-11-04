id: eda-py-3
stage: eda
lang: python
title: Time series of revenue
level: 2
--- task
Load **`data/orders.csv`** with parsed dates, add a `revenue` column
(`quantity * unit_price * (1 - discount)`) and create:

* **`monthly`** – a Series of total revenue per calendar month (use `.resample("MS")` on a date index), covering Jan 2021 – Dec 2024,
* **`yoy`** – a Series of total revenue per **year**, and
* **`growth_2024`** – the percentage growth of 2024 over 2023 (e.g. `12.5` for +12.5%).

Plot `monthly` as a line chart with a 3-month rolling average on top.
--- starter
import pandas as pd
import matplotlib.pyplot as plt

orders = pd.read_csv("data/orders.csv", parse_dates=["order_date"])

monthly = None
yoy = None
growth_2024 = None
--- solution
import pandas as pd
import matplotlib.pyplot as plt

orders = pd.read_csv("data/orders.csv", parse_dates=["order_date"])
orders["revenue"] = orders["quantity"] * orders["unit_price"] * (1 - orders["discount"])

monthly = orders.set_index("order_date")["revenue"].resample("MS").sum()
yoy = orders.groupby(orders["order_date"].dt.year)["revenue"].sum()
growth_2024 = 100 * (yoy[2024] / yoy[2023] - 1)

fig, ax = plt.subplots(figsize=(9, 4))
monthly.plot(ax=ax, alpha=0.5, label="Monthly")
monthly.rolling(3).mean().plot(ax=ax, linewidth=2.5, label="3-month average")
ax.set(title=f"Revenue grew {growth_2024:.0f}% in 2024", xlabel="", ylabel="Revenue")
ax.legend()
plt.show()
print(yoy.round(0))
--- check
import pandas as pd
o = pd.read_csv("data/orders.csv", parse_dates=["order_date"])
o["revenue"] = o["quantity"] * o["unit_price"] * (1 - o["discount"])
y = o.groupby(o["order_date"].dt.year)["revenue"].sum()
expect(isinstance(monthly, pd.Series) and len(monthly) == 48, f"monthly should have 48 months, it has {len(monthly) if monthly is not None else 0}.")
expect(abs(monthly.sum() - o["revenue"].sum()) < 0.01, "monthly should add up to total revenue.")
expect(len(yoy) == 4 and abs(float(yoy.loc[2024]) - y[2024]) < 0.01, "yoy should be revenue per year with years as the index.")
g = 100 * (y[2024] / y[2023] - 1)
expect(abs(float(growth_2024) - g) < 0.01, f"growth_2024 should be {g:.2f} (percent).")
--- hints
- `orders.set_index("order_date")["revenue"].resample("MS").sum()`
- `orders.groupby(orders["order_date"].dt.year)["revenue"].sum()`
- `series.rolling(3).mean()`
