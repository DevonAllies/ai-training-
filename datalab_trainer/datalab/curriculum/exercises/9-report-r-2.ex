id: report-r-2
stage: report
lang: r
title: Tables and figures in an R-generated report
level: 2
--- task
Write a function **`md_table(df)`** that turns a data frame into a Markdown table
(header row, `|---|` separator row, one line per row), then build **`report`** with:

* a `# ` title and an `## Findings` section,
* a Markdown table of churn by plan made with `md_table()` (columns `plan`, `customers`, `churn_pct`),
* a chart saved with `png("reports/churn_by_plan.png")` … `dev.off()` and linked as `![caption](churn_by_plan.png)`.

Save it to **`reports/churn_report_r.md`**. (Open it in any Markdown viewer, or render it with Quarto.)
--- starter
df <- read.csv("data/customers.csv")

md_table <- function(d) {
  ""
}

report <- ""
writeLines(report, "reports/churn_report_r.md")
--- solution
df <- read.csv("data/customers.csv")

md_table <- function(d) {
  head <- paste0("| ", paste(names(d), collapse = " | "), " |")
  sep <- paste0("|", paste(rep("---", ncol(d)), collapse = "|"), "|")
  rows <- apply(d, 1, function(r) paste0("| ", paste(trimws(r), collapse = " | "), " |"))
  paste(c(head, sep, rows), collapse = "\n")
}

by_plan <- data.frame(plan = c("Basic", "Standard", "Premium"))
by_plan$customers <- as.vector(table(df$plan)[by_plan$plan])
by_plan$churn_pct <- sprintf("%.1f%%", 100 * tapply(df$churned, df$plan, mean)[by_plan$plan])

png("reports/churn_by_plan.png", width = 800, height = 500, res = 110)
barplot(100 * tapply(df$churned, df$plan, mean)[by_plan$plan], col = "steelblue", border = NA,
        main = "Basic customers churn most", ylab = "Churn rate (%)")
invisible(dev.off())

report <- paste0(
  "# Basic-plan customers churn almost three times as often as Premium\n\n",
  "## Findings\n\n",
  md_table(by_plan), "\n\n",
  "![Churn rate by plan](churn_by_plan.png)\n"
)
writeLines(report, "reports/churn_report_r.md")
cat(report)
--- check
expect(is.function(md_table), "Define md_table(d).")
t <- md_table(data.frame(a = c(1, 2), b = c("x", "y")))
lines <- strsplit(t, "\n")[[1]]
expect(length(lines) == 4, "md_table() should return a header line, a separator line and one line per row.")
expect(grepl("^\\|\\s*a\\s*\\|\\s*b\\s*\\|$", lines[1]) && grepl("^\\|\\s*:?-{3,}", lines[2]), "The first two lines should be '| a | b |' and '|---|---|'.")
expect(file.exists("reports/churn_report_r.md") && file.exists("reports/churn_by_plan.png"), "Save the report and the PNG chart in reports/.")
expect(startsWith(report, "# ") && grepl("## Findings", report, fixed = TRUE), "The report needs a '# ' title and a '## Findings' section.")
expect(grepl("![", report, fixed = TRUE) && grepl("churn_by_plan.png", report, fixed = TRUE), "Link the chart with ![caption](churn_by_plan.png).")
rate <- mean(read.csv("data/customers.csv")$churned[read.csv("data/customers.csv")$plan == "Basic"])
expect(grepl(sprintf("%.1f%%", 100 * rate), report, fixed = TRUE), "The table should show the Basic churn rate as a percentage with 1 decimal.")
--- hints
- `paste(names(d), collapse = " | ")` joins the column names.
- `apply(d, 1, function(r) ...)` runs once per row.
- `png(file)`, then plot, then `dev.off()` writes the image.
