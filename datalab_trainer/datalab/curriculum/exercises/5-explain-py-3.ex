id: explain-py-3
stage: explain
lang: python
title: Shape results for the report (pivot, melt, segments)
--- task
Turn the analysis into reader-friendly tables:

* **`grid`** – `pd.pivot_table` of churn rate with `region` as rows and `plan` as columns,
  columns in the order `Basic, Standard, Premium`, values rounded to 3 dp.
* **`long`** – `grid` converted back to long format with `reset_index().melt(...)`:
  columns `region, plan, churn_rate` (12 rows).
* **`segments`** – a DataFrame with one row per support-call band (`0-1`, `2-3`, `4+`) and
  columns `customers`, `churn_rate`, `share_of_churners` (share of all churners in that band).
--- starter
import pandas as pd

df = pd.read_csv("data/customers.csv")

grid = None
long = None
segments = None
--- solution
import pandas as pd

df = pd.read_csv("data/customers.csv")

grid = (pd.pivot_table(df, values="churned", index="region", columns="plan", aggfunc="mean")
          [["Basic", "Standard", "Premium"]].round(3))
long = grid.reset_index().melt(id_vars="region", var_name="plan", value_name="churn_rate")

df["band"] = pd.cut(df["support_calls"], [-1, 1, 3, 100], labels=["0-1", "2-3", "4+"])
segments = df.groupby("band", observed=True).agg(customers=("churned", "size"),
                                                  churn_rate=("churned", "mean"),
                                                  churners=("churned", "sum"))
segments["share_of_churners"] = segments["churners"] / segments["churners"].sum()
segments = segments.drop(columns="churners").round(3)
print(grid, long.head(), segments, sep="\n\n")
--- check
import pandas as pd
d = pd.read_csv("data/customers.csv")
g = d.pivot_table(values="churned", index="region", columns="plan", aggfunc="mean")
expect(isinstance(grid, pd.DataFrame) and list(grid.columns) == ["Basic", "Standard", "Premium"],
       "grid columns should be Basic, Standard, Premium (in that order).")
expect(sorted(grid.index) == ["East", "North", "South", "West"], "grid should have one row per region.")
expect(((grid - g[grid.columns].loc[grid.index]).abs() < 0.0006).all().all(), "grid values should be churn rates rounded to 3 dp.")
expect(isinstance(long, pd.DataFrame) and len(long) == 12 and {"region", "plan", "churn_rate"} <= set(long.columns),
       "long should have 12 rows and columns region, plan, churn_rate.")
expect(isinstance(segments, pd.DataFrame) and len(segments) == 3, "segments should have 3 rows (one per band).")
expect({"customers", "churn_rate", "share_of_churners"} <= set(segments.columns), "segments needs customers, churn_rate and share_of_churners.")
expect(abs(segments["share_of_churners"].sum() - 1) < 0.01 and segments["customers"].sum() == 600,
       "share_of_churners should add up to 1 and customers to 600.")
--- hints
- `pd.pivot_table(df, values="churned", index="region", columns="plan", aggfunc="mean")`
- `grid.reset_index().melt(id_vars="region", var_name="plan", value_name="churn_rate")`
- Named aggregation: `.agg(customers=("churned", "size"), churn_rate=("churned", "mean"))`
