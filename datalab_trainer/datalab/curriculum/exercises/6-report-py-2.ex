id: report-py-2
stage: report
lang: python
title: A self-contained HTML report with an embedded chart
level: 2
--- task
Build **`reports/churn_report.html`**: a single HTML file that anyone can open in a browser
(or print to PDF), with the chart embedded so there are no separate image files.

1. Make a bar chart of churn rate by plan with matplotlib and save it into a `BytesIO` buffer as PNG.
2. Encode it with `base64` and embed it as `<img src="data:image/png;base64,...">`.
3. Include an `<h1>` title, a short summary paragraph with the overall churn rate (1 dp %),
   and an HTML `<table>` of churn by plan (`DataFrame.to_html()`).

Set **`html`** to the page's source.
--- starter
import base64
import io
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/customers.csv")

html = ""
--- solution
import base64
import io
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/customers.csv")
rate = df["churned"].mean()
by_plan = (df.groupby("plan")["churned"].agg(customers="size", churn_rate="mean")
             .loc[["Basic", "Standard", "Premium"]])

fig, ax = plt.subplots(figsize=(6, 3.5))
ax.bar(by_plan.index, by_plan["churn_rate"] * 100, color=["#e45756", "#f2a541", "#4c78a8"])
ax.set(title="Basic-plan customers churn most", ylabel="Churn rate (%)")
buf = io.BytesIO()
fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
plt.close(fig)
img = base64.b64encode(buf.getvalue()).decode("ascii")

table = by_plan.assign(churn_rate=lambda t: (t.churn_rate * 100).round(1).astype(str) + "%").to_html()
html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Churn report</title>
<style>body{{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;line-height:1.5}}
table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:4px 8px}}</style></head>
<body>
<h1>Basic-plan customers churn most</h1>
<p>Overall, {rate:.1%} of {len(df):,} customers churned.</p>
<img alt="Churn rate by plan" src="data:image/png;base64,{img}">
{table}
</body></html>"""

with open("reports/churn_report.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Saved reports/churn_report.html,", len(html) // 1024, "KB")
--- check
import os
import pandas as pd
expect(os.path.exists("reports/churn_report.html"), "Save the page to reports/churn_report.html.")
page = open("reports/churn_report.html", encoding="utf-8").read()
expect(isinstance(html, str) and html.strip() and page.strip() == html.strip(),
       "Set html to the page source and write exactly that to reports/churn_report.html.")
expect("<h1" in page.lower(), "Add an <h1> title.")
expect("data:image/png;base64," in page, "Embed the chart as a base64 data URI (data:image/png;base64,...).")
expect("<table" in page.lower(), "Include a table (DataFrame.to_html()).")
r = pd.read_csv("data/customers.csv")["churned"].mean()
expect(f"{r:.1%}" in page, f"Mention the overall churn rate ({r:.1%}).")
--- hints
- `buf = io.BytesIO(); fig.savefig(buf, format="png")`
- `base64.b64encode(buf.getvalue()).decode("ascii")`
- Double the braces `{{ }}` for literal CSS braces inside an f-string.
