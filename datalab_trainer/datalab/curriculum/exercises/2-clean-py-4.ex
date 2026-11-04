id: clean-py-4
stage: clean
lang: python
title: A reusable, validated cleaning function
level: 2
--- task
Put everything together in a function **`clean_customers(raw)`** that takes the raw text DataFrame
and returns the clean one, then:

* add **assertions** at the end of the function (unique ids, allowed regions/plans, ages 18–100, no missing incomes),
* save the result to **`data/my_customers.csv`** (`index=False`, `signup_date` as `YYYY-MM-DD`),
* create **`clean`** = `clean_customers(raw)`.

The check compares `clean` with the answer key on `customer_id, name, region, age, income, plan, signup_date, churned`.
--- starter
import numpy as np
import pandas as pd


def clean_customers(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    # ... your cleaning steps from the previous exercises ...
    return df


raw = pd.read_csv("data/customers_raw.csv", dtype=str, keep_default_na=False)
clean = clean_customers(raw)
clean.to_csv("data/my_customers.csv", index=False)
--- solution
import numpy as np
import pandas as pd

REGIONS = {"N": "North", "S": "South", "E": "East", "W": "West"}


def clean_customers(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.drop_duplicates(subset="customer_id").copy()
    df["name"] = df["name"].str.strip().str.title()
    email = df["email"].str.strip().str.lower()
    df["email"] = email.where(email.str.contains("@", regex=False), np.nan)
    iso = pd.to_datetime(df["signup_date"], format="%Y-%m-%d", errors="coerce")
    dmy = pd.to_datetime(df["signup_date"], format="%d/%m/%Y", errors="coerce")
    df["signup_date"] = iso.fillna(dmy)
    df["region"] = df["region"].str.strip().str.upper().str[0].map(REGIONS)
    age = pd.to_numeric(df["age"], errors="coerce")
    age = age.where(age.between(18, 100))
    df["age"] = age.fillna(age.median()).astype(int)
    income = pd.to_numeric(df["income"].str.replace(r"[$,]", "", regex=True), errors="coerce")
    df["income"] = income.fillna(income.median())
    df["plan"] = df["plan"].str.strip().str.title()
    for c in ["monthly_fee", "monthly_spend"]:
        df[c] = pd.to_numeric(df[c])
    for c in ["tenure_months", "support_calls"]:
        df[c] = pd.to_numeric(df[c]).astype(int)
    df["churned"] = df["churned"].str.strip().str.lower().isin({"yes", "y", "1", "true"}).astype(int)

    assert df["customer_id"].is_unique
    assert df["region"].isin(REGIONS.values()).all()
    assert df["plan"].isin(["Basic", "Standard", "Premium"]).all()
    assert df["age"].between(18, 100).all()
    assert df["income"].notna().all() and df["signup_date"].notna().all()
    return df.sort_values("customer_id").reset_index(drop=True)


raw = pd.read_csv("data/customers_raw.csv", dtype=str, keep_default_na=False)
clean = clean_customers(raw)
clean.to_csv("data/my_customers.csv", index=False, date_format="%Y-%m-%d")
print(clean.head())
--- check
import os
import pandas as pd
expect(callable(clean_customers), "Define a function called clean_customers(raw).")
expect(os.path.exists("data/my_customers.csv"), "Save the result to data/my_customers.csv.")
ref = pd.read_csv("data/customers.csv").set_index("customer_id").sort_index()
c = clean.copy()
c["signup_date"] = pd.to_datetime(c["signup_date"]).dt.strftime("%Y-%m-%d")
c = c.set_index("customer_id").sort_index()
expect(c.index.equals(ref.index), "clean should contain exactly the 600 customers of the answer key.")
for col in ["name", "region", "age", "plan", "signup_date", "churned"]:
    bad = (c[col].astype(str) != ref[col].astype(str)).sum()
    expect(bad == 0, f"Column {col}: {bad} value(s) differ from the answer key.")
expect((c["income"].astype(float) - ref["income"]).abs().max() < 0.01, "Column income differs from the answer key.")
CHECK_MESSAGE = "Your pipeline reproduces the answer key exactly. You can now re-run it on next month's export."
--- hints
- Copy the working code from clean-py-1 to clean-py-3 into the function body.
- An `assert` that fails raises AssertionError. That's the point: bad data stops the pipeline.
