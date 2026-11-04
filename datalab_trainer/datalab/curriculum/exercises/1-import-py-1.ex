id: import-py-1
stage: import
lang: python
title: Read a messy CSV safely with pandas
--- task
Read **`data/customers_raw.csv`** into a DataFrame called **`raw`**, keeping **every column as text**
and leaving empty cells as empty strings (so nothing is converted behind your back).

Then create:

* `n_rows` – number of rows
* `n_dupes` – number of rows whose `customer_id` already appeared earlier in the file

Print `raw.head()` and `raw.dtypes` to see what you are working with.
--- starter
import pandas as pd

raw = pd.read_csv("data/customers_raw.csv")   # TODO: read everything as text, keep "" as ""

n_rows = None    # TODO
n_dupes = None   # TODO

print(raw.head())
print(raw.dtypes)
--- solution
import pandas as pd

raw = pd.read_csv("data/customers_raw.csv", dtype=str, keep_default_na=False)

n_rows = len(raw)
n_dupes = int(raw["customer_id"].duplicated().sum())

print(raw.head())
print(raw.dtypes)
print(f"{n_rows} rows, {n_dupes} duplicated customer_id values")
--- check
import pandas as pd
expect(isinstance(raw, pd.DataFrame), "`raw` should be a pandas DataFrame.")
expect(raw.shape == (618, 13), f"`raw` should have 618 rows and 13 columns, it has {raw.shape}.")
expect(all(pd.api.types.is_string_dtype(raw[c]) or raw[c].dtype == object for c in raw.columns)
       and not pd.api.types.is_numeric_dtype(raw["monthly_fee"]),
       "Every column should be text. Pass dtype=str to read_csv.")
expect(raw["income"].isna().sum() == 0,
       "Empty cells became NaN. Pass keep_default_na=False to keep them as empty strings.")
expect(n_rows == 618, "n_rows should be the number of rows (len(raw)).")
expect(n_dupes == 18, f"n_dupes should be 18, you have {n_dupes}. Try raw['customer_id'].duplicated().sum().")
CHECK_MESSAGE = "Correct: 618 rows, 18 duplicates. Every value is still exactly as it is in the file."
--- hints
- `pd.read_csv(path, dtype=str, keep_default_na=False)`
- `Series.duplicated()` is True for the second and later copies of a value; `.sum()` counts them.
