# DataLab Trainer – data analysis & data science, end to end

DataLab Trainer is a local training app for learning the **whole analytics workflow** in
**SQL, Python and R**:

```
Import  →  Clean  →  Explore (EDA)  →  Model  →  Explain (SHAP) & Shape  →  Report
```

You work as an analyst for *Ridgeway Retail*, a fictional subscription retailer, and
answer a real business question: *which customers churn, why, and what should we do about it?*
Every stage has a lesson, auto-checked exercises in all three languages and a quiz. Then
you do a **capstone project** on a new, messy dataset and write it up in the built-in
**Report Builder**.

It runs **natively on Windows and Ubuntu**, with no Wine, Bottles, WSL or virtual machine. It's a
small Python web server bound to your own computer (`http://127.0.0.1:8070`) and it uses
your browser as the interface. It works offline.

## What's inside

| | |
|---|---|
| **6 stages** | Import · Clean · Explore · Model · Explain & Shape · Report. Each lesson's code samples switch between SQL / Python / R |
| **44 exercises** | starter code, hints, a model solution and an **automatic checker** for each. Core and *stretch* levels |
| **25 quiz questions** | concept checks with explanations |
| **Capstone project** | daily bike-rental demand: messy raw data, a validator for your cleaned file, guided steps, notes |
| **Playground** | free coding in any language against the same datasets, with snippets |
| **Datasets browser** | preview and profile every file, with code to load it in each language |
| **Report Builder** | sectioned report template, insert charts from your runs, a rubric that checks your draft, export to self-contained HTML / Markdown, print to PDF |
| **Progress tracking** | dashboard with a stage × language matrix; your code is auto-saved |

### What you learn at each stage

| Stage | SQL (DuckDB) | Python | R |
|---|---|---|---|
| **Import** | `read_csv_auto`, `read_json_auto`, `DESCRIBE` | pandas CSV/JSON, `sqlite3`, dtypes | `read.csv`, `colClasses`, `as.Date` |
| **Clean** | `QUALIFY` de-dup, `CASE` mapping, `TRY_CAST`, `try_strptime`, window medians | `drop_duplicates`, `.str`, `to_numeric`, imputation, explicit date formats, assertions, a reusable cleaning function | `duplicated`, `trimws`, `gsub`, lookup vectors, `stopifnot` |
| **EDA** | group rates, `date_trunc`, `corr`, `quantile_cont`, segments | `describe`, `groupby`, `pd.cut`, matplotlib charts, correlation matrix, resampling | `summary`, `tapply`, `cut`, `hist`/`boxplot`, `cor` |
| **Model** | `regr_slope/intercept/r2`, feature tables with joins, confusion matrix of a rule | train/test split, `LinearRegression`, pipelines + `LogisticRegression`, ROC AUC, cross-validation, random forest | `lm`, `glm(binomial)`, odds ratios, AUC by hand |
| **Explain & Shape** | linear SHAP values in SQL, `PIVOT`/conditional aggregation | **SHAP by hand** (additivity), **`shap.TreeExplainer`** beeswarm, `pivot_table`/`melt` | SHAP by hand for `lm`, cross-tabs, long format |
| **Report** | KPI table for the summary | Markdown and **self-contained HTML reports generated from code** | `sprintf`/`writeLines` reports (→ R Markdown / Quarto) |

## Install

### Windows 10 / 11

1. Install **Python 3.10 or newer** from <https://www.python.org/downloads/>. Tick **"Add python.exe to PATH"** in the installer.
2. *(For the R exercises)* install **R** from <https://cran.r-project.org/bin/windows/base/> with the default options.
   DataLab finds `Rscript.exe` under `C:\Program Files\R\` automatically.
3. Double-click **`install.bat`** in this folder (once). It creates a private `.venv` and installs the Python packages.
4. Double-click **`run.bat`**. Your browser opens DataLab. Close the black window to stop it.

### Ubuntu (22.04 / 24.04) and other Linux

```bash
sudo apt update
sudo apt install python3 python3-venv r-base   # r-base is only needed for the R exercises
cd datalab_trainer
./install.sh     # once
./run.sh         # starts DataLab and opens your browser; Ctrl+C stops it
```

### Optional R packages

The checked R exercises use **base R only**, so nothing else is required. Lessons also show
tidyverse / ggplot2 / SHAP-for-R equivalents. To install those packages:

```bash
Rscript setup_r_packages.R
```

The **Setup & environment** page in the app shows what's installed, the exact command to
install anything missing, and lets you point DataLab to a different Python or `Rscript`.

### Options

```
run.bat --port 9000         ./run.sh --port 9000      # different port
run.bat --no-browser        ./run.sh --no-browser     # don't open the browser
```

## Where your work is kept

| | Windows | Linux |
|---|---|---|
| Progress, saved code, quiz scores, report draft | `%APPDATA%\DataLabTrainer\progress.json` | `~/.local/share/datalab-trainer/progress.json` |
| Workspace (your code runs here) | `%APPDATA%\DataLabTrainer\workspace` | `~/.local/share/datalab-trainer/workspace` |

The workspace contains `data/` (a copy of the datasets: break them freely and restore them from the
Datasets page), `figures/` (every chart you make) and `reports/` (exported reports).
Set the `DATALAB_HOME` environment variable to keep everything somewhere else, e.g. on a USB stick.

## How code runs

* **SQL** runs on an embedded **DuckDB** database. Every CSV in `data/` is available as a view
  named after the file (`customers`, `customers_raw`, `orders`, `rentals_raw`, plus `products`).
* **Python** runs in a separate process (the `.venv` interpreter by default), so an error
  or endless loop can't crash the app. `plt.show()` charts are captured.
* **R** runs through `Rscript`. Base graphics and ggplot charts (`print(p)`) are captured.
* Each run has a time limit (120 s by default, adjustable on the Setup page).
* Checks look at what your code produced (variables, files or the SQL result) and give
  a specific message when something's wrong. SQL results are compared with the model
  solution, ignoring row order unless the task says otherwise.

The server only listens on `127.0.0.1` and rejects requests from other websites, because it runs code.

## The datasets

All data is synthetic and generated by `tools/make_datasets.py` with a fixed seed.

| File | Rows | Notes |
|---|---|---|
| `customers_raw.csv` | 618 | messy CRM export: 18 duplicates, mixed case & spacing, `"$55,600"` incomes, impossible ages, DD/MM/YYYY and ISO dates, 10 spellings of yes/no |
| `customers.csv` | 600 | the cleaned answer key (produced by `datalab/reference.py`) |
| `orders.csv` | 4,000 | orders 2021–2024 |
| `products.json` | 6 | product categories and margins |
| `ridgeway.db` | – | SQLite: `stores`, `targets` |
| `rentals_raw.csv` | 736 | capstone: daily bike rentals with duplicates, `"65%"` humidity, missing temperatures and a `-99` sensor code |

## For trainers: adding content

* A stage is a Markdown file in `datalab/curriculum/stages/` with a `--- lesson` and a `--- quiz` section.
* An exercise is a text file in `datalab/curriculum/exercises/` with a short header
  (`id`, `stage`, `lang`, `title`, optional `level`, `ordered`, `needs`) and sections
  `--- task`, `--- starter`, `--- solution`, `--- check`, `--- hints`.
  * Python / R checks run after the learner's code in the same session and call
    `expect(condition, "message")`. Set `CHECK_MESSAGE` for a custom success message.
  * SQL exercises need no check: the learner's result is compared with the solution's.
* Run the tests. They run **every solution through its checker** (and confirm every starter
  doesn't pass yet) in all three languages:

```bash
.venv/bin/python -m pip install pytest      # Windows: .venv\Scripts\python -m pip install pytest
.venv/bin/python -m pytest -q tests
```

GitHub Actions runs the same tests on Ubuntu and Windows with R installed (`.github/workflows/datalab.yml`).
