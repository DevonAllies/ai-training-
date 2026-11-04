id: report-r-1
stage: report
lang: r
title: Generate a Markdown report from R
--- task
Build a Markdown report as a single character string **`report`** with `sprintf()` / `paste0()`,
and save it with `writeLines()` to **`reports/churn_summary_r.md`**.

It must contain:

* a `# ` title that states the main finding,
* sections `## Executive summary`, `## Findings`, `## Recommendations`, `## Limitations`,
* the overall churn rate as a percentage with 1 decimal (e.g. `22.8%`, use `sprintf("%.1f%%", 100 * rate)`),
* at least two bullet-point recommendations.

*Next step:* the same text in an `.Rmd` or `.qmd` file can be rendered to HTML/Word/PDF
with `rmarkdown::render()` or `quarto render`.
--- starter
df <- read.csv("data/customers.csv")
rate <- mean(df$churned)

report <- paste0("# Title\n\nChurn is ", rate, "\n")
writeLines(report, "reports/churn_summary_r.md")
cat(report)
--- solution
df <- read.csv("data/customers.csv")
rate <- mean(df$churned)
by_plan <- tapply(df$churned, df$plan, mean)
pct <- function(x) sprintf("%.1f%%", 100 * x)

report <- paste0(
  "# Support problems and the Basic plan drive churn at Ridgeway\n\n",
  "## Executive summary\n",
  sprintf("%s of %d customers churned. Basic-plan customers churn at %s versus %s on Premium.\n\n",
          pct(rate), nrow(df), pct(by_plan["Basic"]), pct(by_plan["Premium"])),
  "## Findings\n",
  sprintf("- Overall churn rate: %s.\n", pct(rate)),
  sprintf("- Average monthly spend: %.2f.\n\n", mean(df$monthly_spend)),
  "## Recommendations\n",
  "- Call customers proactively after their third support call.\n",
  "- Offer Basic customers an upgrade in their first six months.\n\n",
  "## Limitations\n",
  "- Observational data: associations, not proven causes.\n"
)
writeLines(report, "reports/churn_summary_r.md")
cat(report)
--- check
expect(is.character(report) && length(report) == 1, "report should be a single character string (use paste0).")
expect(file.exists("reports/churn_summary_r.md"), "Save it to reports/churn_summary_r.md with writeLines().")
first <- strsplit(report, "\n")[[1]][1]
expect(startsWith(first, "# ") && tolower(trimws(first)) != "# title", "Start with a '# ' title that states the main finding.")
for (s in c("## executive summary", "## findings", "## recommendations", "## limitations"))
  expect(grepl(s, tolower(report), fixed = TRUE), paste("Missing section:", s))
rate <- mean(read.csv("data/customers.csv")$churned)
expect(grepl(sprintf("%.1f%%", 100 * rate), report, fixed = TRUE), sprintf("Quote the churn rate as %.1f%%.", 100 * rate))
rec <- strsplit(strsplit(tolower(report), "## recommendations", fixed = TRUE)[[1]][2], "##", fixed = TRUE)[[1]][1]
expect(sum(grepl("^\\s*[-*] ", strsplit(rec, "\n")[[1]])) >= 2, "Give at least two bullet-point recommendations.")
--- hints
- `sprintf("%.1f%%", 100 * rate)` - `%%` prints a literal percent sign.
- `paste0()` glues strings; `"\n"` is a new line.
