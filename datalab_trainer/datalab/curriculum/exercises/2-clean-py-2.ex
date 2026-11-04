id: clean-py-2
stage: clean
lang: python
title: Convert text to numbers, fix impossible values, impute
--- task
Continue cleaning (the starter already removes duplicates). Make these columns correct:

* `income` – numeric (remove `$` and `,`); fill missing values with the **median** income.
  Store how many values you filled in **`n_income_imputed`**.
* `age` – numeric; values outside **18–100** are errors → treat as missing; fill missing with
  the **median** of the valid ages; store as integer.
* `churned` – `1` for Yes / Y / 1 / TRUE (any case), otherwise `0`, as integer.

The check compares your columns with the answer key `data/customers.csv`.
--- starter
import pandas as pd

raw = pd.read_csv("data/customers_raw.csv", dtype=str, keep_default_na=False)
df = raw.drop_duplicates(subset="customer_id").copy()

# income
df["income"] = df["income"]          # TODO
n_income_imputed = 0                  # TODO

# age
df["age"] = df["age"]                # TODO

# churned
df["churned"] = df["churned"]        # TODO

print(df[["income", "age", "churned"]].describe())
--- solution
import pandas as pd

raw = pd.read_csv("data/customers_raw.csv", dtype=str, keep_default_na=False)
df = raw.drop_duplicates(subset="customer_id").copy()

income = pd.to_numeric(df["income"].str.replace(r"[$,]", "", regex=True), errors="coerce")
n_income_imputed = int(income.isna().sum())
df["income"] = income.fillna(income.median())

age = pd.to_numeric(df["age"], errors="coerce")
age = age.where(age.between(18, 100))           # impossible values -> NaN
df["age"] = age.fillna(age.median()).astype(int)

yes = {"yes", "y", "1", "true"}
df["churned"] = df["churned"].str.strip().str.lower().isin(yes).astype(int)

print(df[["income", "age", "churned"]].describe())
print(n_income_imputed, "incomes imputed")
--- check
import pandas as pd
ref = pd.read_csv("data/customers.csv").set_index("customer_id")
d = df.drop_duplicates("customer_id").set_index("customer_id")
expect(len(d) == 600, "Keep one row per customer (600 rows).")
expect(pd.api.types.is_numeric_dtype(d["income"]), "income should be numeric.")
expect(d["income"].notna().all(), "income still has missing values: fill them with the median.")
_blank = int((pd.read_csv("data/customers_raw.csv", dtype=str, keep_default_na=False)
              .drop_duplicates("customer_id")["income"].str.strip() == "").sum())
expect(n_income_imputed == _blank, f"n_income_imputed should be {_blank} (the number of blank incomes), you have {n_income_imputed}.")
diff = (d["income"] - ref.loc[d.index, "income"]).abs().max()
expect(diff < 0.01, "Some income values don't match. Did you remove both $ and , and use the median of the parsed values?")
expect(pd.api.types.is_integer_dtype(d["age"]), "age should be an integer column (.astype(int)).")
expect(d["age"].between(18, 100).all(), "age still has values outside 18-100.")
expect((d["age"] == ref.loc[d.index, "age"]).all(), "Some ages don't match: set out-of-range ages to NaN *before* computing the median.")
expect(set(d["churned"].unique()) <= {0, 1}, "churned should only contain 0 and 1.")
expect((d["churned"] == ref.loc[d.index, "churned"]).all(), "Some churned values are wrong. Did you handle Y, 1 and TRUE, in any case?")
CHECK_MESSAGE = "All numeric columns are clean and match the answer key."
--- hints
- `pd.to_numeric(s.str.replace(r"[$,]", "", regex=True), errors="coerce")` - blanks become NaN.
- `age.where(age.between(18, 100))` keeps valid ages and turns the rest into NaN.
- `s.str.strip().str.lower().isin({"yes", "y", "1", "true"}).astype(int)`
