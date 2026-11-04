id: report-py-1
stage: report
lang: python
title: Generate a Markdown report from code
--- task
Write a short report as a Markdown string called **`report`**, with **every number calculated
by code** (f-strings), and save it to **`reports/churn_summary.md`**.

It must contain:

* a title line starting with `# ` that states the main finding,
* sections `## Executive summary`, `## Findings`, `## Recommendations`, `## Limitations`,
* the overall churn rate formatted as a percentage with 1 decimal (e.g. `22.8%`),
* the churn rate of the Basic and Premium plans,
* at least 2 recommendations as bullet points (`- `).
--- starter
import pandas as pd

df = pd.read_csv("data/customers.csv")
rate = df["churned"].mean()

report = f"""# Title

## Executive summary
Churn rate is {rate}.
"""

with open("reports/churn_summary.md", "w", encoding="utf-8") as f:
    f.write(report)
print(report)
--- solution
import pandas as pd

df = pd.read_csv("data/customers.csv")
rate = df["churned"].mean()
by_plan = df.groupby("plan")["churned"].mean()
calls_hi = df.loc[df.support_calls >= 4, "churned"].mean()
calls_lo = df.loc[df.support_calls <= 1, "churned"].mean()

report = f"""# Support problems and the Basic plan drive churn at Ridgeway

## Executive summary
{rate:.1%} of Ridgeway's {len(df):,} customers churned. Risk is concentrated in customers who
contact support often ({calls_hi:.0%} churn with 4+ calls vs {calls_lo:.0%} with 0-1) and on the
Basic plan ({by_plan['Basic']:.1%} vs {by_plan['Premium']:.1%} on Premium). Fixing the causes of
repeat support calls is the most promising retention lever.

## Findings
- Overall churn rate: {rate:.1%}.
- Basic plan churn: {by_plan['Basic']:.1%}; Standard: {by_plan['Standard']:.1%}; Premium: {by_plan['Premium']:.1%}.
- Churn rises with support calls: {calls_lo:.0%} (0-1 calls) to {calls_hi:.0%} (4+ calls).

## Recommendations
- Flag customers after their 3rd support call for a proactive call from a senior agent.
- Test an upgrade offer from Basic to Standard for customers in their first 6 months.

## Limitations
- Data is observational, so these are associations, not proven causes.
- About 5% of incomes and ages were missing or impossible and were filled with the median during cleaning.
"""

with open("reports/churn_summary.md", "w", encoding="utf-8") as f:
    f.write(report)
print(report)
--- check
import os
import pandas as pd
d = pd.read_csv("data/customers.csv")
expect(isinstance(report, str), "report should be a string.")
expect(os.path.exists("reports/churn_summary.md"), "Save the report to reports/churn_summary.md.")
saved = open("reports/churn_summary.md", encoding="utf-8").read()
expect(saved.strip() == report.strip(), "The saved file should contain the report string.")
lines = report.strip().splitlines()
expect(lines and lines[0].startswith("# ") and lines[0].strip().lower() != "# title", "Start with a '# ' title that states the main finding.")
for sec in ["## Executive summary", "## Findings", "## Recommendations", "## Limitations"]:
    expect(sec.lower() in report.lower(), f"Missing section: {sec}")
r = d["churned"].mean()
expect(f"{r:.1%}" in report, f"Quote the overall churn rate as a percentage with 1 decimal ({r:.1%}), calculated by code.")
bp = d.groupby("plan")["churned"].mean()
expect(any(f"{bp['Basic']*100:.{k}f}%" in report for k in (0, 1)) and any(f"{bp['Premium']*100:.{k}f}%" in report for k in (0, 1)),
       "Quote the Basic and Premium churn rates as percentages.")
rec = report.lower().split("## recommendations", 1)[1].split("##", 1)[0]
expect(sum(1 for l in rec.splitlines() if l.strip().startswith(("- ", "* "))) >= 2, "Give at least two bullet-point recommendations.")
CHECK_MESSAGE = "Report generated from code. Re-run it next month and every number updates itself."
--- hints
- `f"{rate:.1%}"` formats 0.228 as `22.8%`.
- Triple-quoted f-strings can span many lines.
- `by_plan = df.groupby("plan")["churned"].mean()`, then `by_plan['Basic']`.
