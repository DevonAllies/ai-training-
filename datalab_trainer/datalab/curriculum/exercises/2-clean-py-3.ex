id: clean-py-3
stage: clean
lang: python
title: Mixed date formats and invalid emails
--- task
`signup_date` mixes ISO dates (`2021-08-24`) and day-first dates (`26/03/2024`).

1. Convert `signup_date` to datetime by parsing **each format explicitly** and combining them.
   Every row must end up with a valid date.
2. Lower-case and trim `email`; emails without `@` (or blank) become missing (`NaN`).
3. Set **`tenure_check`**: the number of customers who signed up in **2024**.

Don't use `pd.to_datetime(..., dayfirst=True)` on the whole column. It quietly gets the ISO dates wrong in some pandas versions. Be explicit.
--- starter
import numpy as np
import pandas as pd

raw = pd.read_csv("data/customers_raw.csv", dtype=str, keep_default_na=False)
df = raw.drop_duplicates(subset="customer_id").copy()

df["signup_date"] = pd.to_datetime(df["signup_date"], errors="coerce")   # TODO handle both formats
print(df["signup_date"].isna().sum(), "dates failed to parse")

# TODO emails

tenure_check = None
--- solution
import numpy as np
import pandas as pd

raw = pd.read_csv("data/customers_raw.csv", dtype=str, keep_default_na=False)
df = raw.drop_duplicates(subset="customer_id").copy()

iso = pd.to_datetime(df["signup_date"], format="%Y-%m-%d", errors="coerce")
dmy = pd.to_datetime(df["signup_date"], format="%d/%m/%Y", errors="coerce")
df["signup_date"] = iso.fillna(dmy)
print(df["signup_date"].isna().sum(), "dates failed to parse")

email = df["email"].str.strip().str.lower()
df["email"] = email.where(email.str.contains("@", regex=False), np.nan)

tenure_check = int((df["signup_date"].dt.year == 2024).sum())
print(tenure_check, "customers signed up in 2024")
--- check
import pandas as pd
ref = pd.read_csv("data/customers.csv", parse_dates=["signup_date"]).set_index("customer_id")
d = df.drop_duplicates("customer_id").set_index("customer_id")
expect(pd.api.types.is_datetime64_any_dtype(d["signup_date"]), "signup_date should be a datetime column.")
expect(d["signup_date"].notna().all(), "Some dates are still missing: parse the DD/MM/YYYY ones with a second format.")
expect((d["signup_date"] == ref.loc[d.index, "signup_date"]).all(),
       "Some dates are wrong. Did 05/01/2023 become 5 January (correct) or 1 May?")
expect(d["email"].isna().sum() == ref["email"].isna().sum(),
       f"Expected {ref['email'].isna().sum()} missing emails (blank or without @), you have {d['email'].isna().sum()}.")
expect(tenure_check == int((ref["signup_date"].dt.year == 2024).sum()), "tenure_check should count 2024 sign-ups.")
--- hints
- `pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")` parses only that format and gives NaT for the rest.
- Combine two partial results with `a.fillna(b)`.
- `s.where(condition, np.nan)` keeps values where the condition is True.
