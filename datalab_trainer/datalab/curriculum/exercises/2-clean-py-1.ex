id: clean-py-1
stage: clean
lang: python
title: Duplicates, whitespace and inconsistent labels
--- task
Starting from the raw text data, build a DataFrame **`df`** where:

1. there is exactly **one row per `customer_id`** (drop the duplicates),
2. `name` has no leading/trailing spaces and is in Title Case (`"  sipho mahlangu "` → `"Sipho Mahlangu"`),
3. `region` is one of `North`, `South`, `East`, `West`,
4. `plan` is one of `Basic`, `Standard`, `Premium`.

Print `df["region"].value_counts()` before and after to see the effect.
--- starter
import pandas as pd

raw = pd.read_csv("data/customers_raw.csv", dtype=str, keep_default_na=False)
print(raw["region"].value_counts())

df = raw.copy()
# 1. drop duplicate customers
# 2. tidy name
# 3. standardise region (hint: first letter after strip/upper)
# 4. tidy plan

print(df["region"].value_counts())
--- solution
import pandas as pd

raw = pd.read_csv("data/customers_raw.csv", dtype=str, keep_default_na=False)
print(raw["region"].value_counts())

df = raw.drop_duplicates(subset="customer_id", keep="first").copy()
df["name"] = df["name"].str.strip().str.title()
region_map = {"N": "North", "S": "South", "E": "East", "W": "West"}
df["region"] = df["region"].str.strip().str.upper().str[0].map(region_map)
df["plan"] = df["plan"].str.strip().str.title()

print(df["region"].value_counts())
print(len(raw) - len(df), "duplicate rows removed")
--- check
expect(len(df) == 600, f"df should have 600 rows (one per customer), it has {len(df)}.")
expect(df["customer_id"].is_unique, "customer_id should be unique.")
expect((df["name"] == df["name"].str.strip()).all(), "Some names still have leading/trailing spaces: use .str.strip().")
expect((df["name"] == df["name"].str.title()).all(), "Names should be Title Case: use .str.title().")
bad = sorted(set(df["region"].dropna()) - {"North", "South", "East", "West"})
expect(not bad and df["region"].notna().all(), f"region still has other values: {bad or 'missing values'}.")
expect(set(df["plan"]) == {"Basic", "Standard", "Premium"}, f"plan values should be Basic/Standard/Premium, got {sorted(set(df['plan']))}.")
CHECK_MESSAGE = "Clean: 600 unique customers with tidy names, regions and plans."
--- hints
- `raw.drop_duplicates(subset="customer_id")`
- String methods chain: `s.str.strip().str.title()`
- `s.str.strip().str.upper().str[0]` gives the first letter; `.map({"N": "North", ...})` turns it into a name.
