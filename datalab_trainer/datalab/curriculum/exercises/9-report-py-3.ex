id: report-py-3
stage: report
lang: python
title: An Excel deliverable for stakeholders
--- task
Many managers want the numbers in **Excel**. Write **`reports/churn_tables.xlsx`** with
`pd.ExcelWriter(..., engine="openpyxl")` containing three sheets:

* **`Summary`** – one row: customers, churn_pct, avg_spend
* **`By plan`** – plan, customers, churn_pct (sorted high to low)
* **`High risk`** – the customers with **4+ support calls and tenure under 12 months**:
  customer_id, name, plan, tenure_months, support_calls (a list the retention team can call)

Set **`n_high_risk`** to the number of customers on that list. Round percentages to 1 dp.
--- starter
import pandas as pd

df = pd.read_csv("data/customers.csv")

n_high_risk = None
# with pd.ExcelWriter("reports/churn_tables.xlsx", engine="openpyxl") as xl:
#     some_df.to_excel(xl, sheet_name="Summary", index=False)
--- solution
import pandas as pd

df = pd.read_csv("data/customers.csv")

summary = pd.DataFrame([{
    "customers": len(df),
    "churn_pct": round(100 * df["churned"].mean(), 1),
    "avg_spend": round(df["monthly_spend"].mean(), 2),
}])
by_plan = (df.groupby("plan").agg(customers=("churned", "size"), churn_pct=("churned", "mean"))
             .assign(churn_pct=lambda t: (100 * t.churn_pct).round(1))
             .sort_values("churn_pct", ascending=False).reset_index())
high_risk = (df.loc[(df.support_calls >= 4) & (df.tenure_months < 12),
                    ["customer_id", "name", "plan", "tenure_months", "support_calls"]]
               .sort_values(["support_calls", "tenure_months"], ascending=[False, True]))
n_high_risk = len(high_risk)

with pd.ExcelWriter("reports/churn_tables.xlsx", engine="openpyxl") as xl:
    summary.to_excel(xl, sheet_name="Summary", index=False)
    by_plan.to_excel(xl, sheet_name="By plan", index=False)
    high_risk.to_excel(xl, sheet_name="High risk", index=False)
print(summary, by_plan, f"{n_high_risk} high-risk customers", sep="\n\n")
--- check
import os
import pandas as pd
p = "reports/churn_tables.xlsx"
expect(os.path.exists(p), "Write the workbook to reports/churn_tables.xlsx.")
sheets = pd.read_excel(p, sheet_name=None)
expect({"Summary", "By plan", "High risk"} <= set(sheets), f"The workbook needs the sheets Summary, By plan and High risk (found {list(sheets)}).")
d = pd.read_csv("data/customers.csv")
s = sheets["Summary"]
expect(len(s) == 1 and abs(float(s["churn_pct"].iloc[0]) - round(100 * d.churned.mean(), 1)) < 0.051, "Summary should have one row with churn_pct (1 dp).")
bp = sheets["By plan"]
expect(len(bp) == 3 and bp["churn_pct"].is_monotonic_decreasing, "By plan should have 3 rows sorted by churn_pct, high to low.")
exp = int(((d.support_calls >= 4) & (d.tenure_months < 12)).sum())
expect(n_high_risk == exp and len(sheets["High risk"]) == exp, f"High risk should list the {exp} customers with 4+ calls and tenure under 12 months.")
expect({"customer_id", "name"} <= set(sheets["High risk"].columns), "High risk needs customer_id and name so the team can call them.")
CHECK_MESSAGE = f"Workbook ready: {exp} customers on the call list."
--- hints
- `with pd.ExcelWriter(path, engine="openpyxl") as xl:` then `df.to_excel(xl, sheet_name="...", index=False)` for each sheet.
- Filter: `df[(df.support_calls >= 4) & (df.tenure_months < 12)]`
