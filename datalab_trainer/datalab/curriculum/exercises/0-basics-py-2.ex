id: basics-py-2
stage: basics
lang: python
title: First steps with pandas
--- task
Load `data/customers.csv` into **`df`** and create:

* **`n_customers`** – the number of rows
* **`premium_north`** – a DataFrame of Premium customers in the North region, with only the columns
  `customer_id`, `name`, `monthly_spend`, sorted by `monthly_spend` from high to low
* a new column **`df["annual_spend"]`** = `monthly_spend` × 12
* **`avg_income`** – the average income (`.mean()`)
--- starter
import pandas as pd

df = pd.read_csv("data/customers.csv")
print(df.head())

n_customers = None
premium_north = None
avg_income = None
--- solution
import pandas as pd

df = pd.read_csv("data/customers.csv")
print(df.head())

n_customers = len(df)
mask = (df["plan"] == "Premium") & (df["region"] == "North")
premium_north = (df.loc[mask, ["customer_id", "name", "monthly_spend"]]
                   .sort_values("monthly_spend", ascending=False))
df["annual_spend"] = df["monthly_spend"] * 12
avg_income = df["income"].mean()
print(n_customers, round(avg_income), premium_north.head(), sep="\n")
--- check
import pandas as pd
ref = pd.read_csv("data/customers.csv")
expect(n_customers == 600, "n_customers should be len(df) = 600.")
expect(isinstance(premium_north, pd.DataFrame) and list(premium_north.columns) == ["customer_id", "name", "monthly_spend"],
       "premium_north should have exactly the columns customer_id, name, monthly_spend.")
exp = ref[(ref.plan == "Premium") & (ref.region == "North")]
expect(len(premium_north) == len(exp), f"premium_north should have {len(exp)} rows (Premium AND North).")
expect(premium_north["monthly_spend"].is_monotonic_decreasing, "Sort premium_north by monthly_spend, highest first.")
expect("annual_spend" in df.columns and (df["annual_spend"] == df["monthly_spend"] * 12).all(), "Add df['annual_spend'] = monthly_spend * 12.")
expect(abs(avg_income - ref["income"].mean()) < 1e-6, "avg_income should be df['income'].mean().")
--- hints
- Combine conditions: `(df["plan"] == "Premium") & (df["region"] == "North")`.
- `df.loc[mask, [columns]]` filters rows and picks columns in one step.
- `.sort_values("monthly_spend", ascending=False)`
