id: report
title: Report
summary: Turn the analysis into a clear, honest, reproducible report that leads to a decision.
--- lesson
# Module 9 · Report writing

The report is the product. Most readers only read the first paragraph, so **lead with the
answer** and keep the method for later sections.

## A structure that works

| Section | What goes in it | Length |
|---|---|---|
| **Title** | the main finding, not the topic: *"Support problems drive churn at Ridgeway"* | 1 line |
| **Executive summary** | question → answer → key numbers → recommendation | ≤ 150 words |
| **Question & context** | why this matters, who asked, what decision it supports | short |
| **Data** | sources, period, rows, what was cleaned / removed / imputed | short + table |
| **Findings (EDA)** | 3–5 findings, each a sentence with a number + one chart | main body |
| **Model** | what was predicted, method, test-set metric vs baseline | short |
| **Explanation** | which drivers matter and in which direction (SHAP) | chart + text |
| **Recommendations** | concrete actions, owner, expected impact | bullets |
| **Limitations & next steps** | data gaps, assumptions, what you'd do with more time | bullets |
| **Appendix** | code location, full tables, definitions | optional |

## Writing rules

1. **Numbers in sentences.** Not "churn is higher for Basic" but "Basic customers churn at 31%, Premium at 11%."
2. **Round sensibly.** 30.9%, not 30.882352941%. Two significant figures is often enough.
3. **One idea per chart**, with the finding as the chart title and a caption saying what to notice.
4. **Plain words.** "AUC of 0.80 (a random churner is ranked above a random stayer 80% of the time)."
5. **Be honest about uncertainty**: sample sizes, imputation, correlation ≠ causation.
6. **Recommendations follow from findings.** Each one should point back to a number.

## Reproducible reports: put the numbers in with code

Never copy numbers into a document by hand. They go stale and pick up typos. Let code write them:

```sql
-- a KPI table the report can quote
SELECT count(*) AS customers, round(100 * avg(churned), 1) AS churn_pct,
       round(avg(monthly_spend), 2) AS avg_spend FROM customers;
```
```python
rate = df["churned"].mean()
report = f"""# Support problems drive churn

**Churn rate:** {rate:.1%} of {len(df):,} customers.
"""
open("reports/summary.md", "w", encoding="utf-8").write(report)
```
```r
rate <- mean(df$churned)
report <- sprintf("# Support problems drive churn\n\n**Churn rate:** %.1f%% of %d customers.\n",
                  100 * rate, nrow(df))
writeLines(report, "reports/summary.md")
```

Tools that combine code and text in one document:
* **Jupyter notebooks** (Python, also R) — `jupyter nbconvert --to html analysis.ipynb`
* **Quarto** (Python, R, SQL; Windows & Linux) — `quarto render report.qmd` → HTML / Word / PDF
* **R Markdown** — `rmarkdown::render("report.Rmd")`

DataLab's **Report Builder** (left menu) gives you the section structure above, inserts
figures from your runs, checks your draft against a rubric and exports a self-contained
HTML file you can print to PDF from any browser.

## Self-review checklist before sending

- [ ] Could a busy manager act on the executive summary alone?
- [ ] Does every finding contain a number and a comparison?
- [ ] Are the model's limits and the data cleaning steps stated?
- [ ] Are charts titled with the message, axes labelled, sources noted?
- [ ] Can someone else re-run the code and get the same numbers?
--- quiz
Q: What belongs in the first paragraph of an analytical report?
- The data cleaning steps
- The code
* The answer to the question, the key numbers and the recommendation
- A history of the company
E: Lead with the conclusion. The method comes later.
Q: Which finding is written best?
- Churn is kind of high for some plans
- Basic plan churn: 0.3088235294
* Basic-plan customers churn at 31%, almost three times the Premium rate (11%)
E: A rounded number with a comparison tells the reader what it means.
Q: Why should code generate the numbers in a report?
* So the report updates when the data changes, without copy-paste errors
- Because Word can't show numbers
- It makes the report longer
E: That's reproducibility: re-run, and the document is up to date.
Q: Which belongs in "Limitations"?
- The final recommendation
* 5% of incomes were missing and filled with the median
- The executive summary
E: Readers need to know what the analysis assumed, so they know how far to trust it.
