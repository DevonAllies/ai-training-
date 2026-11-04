id: visualise-sql-1
stage: visualise
lang: sql
title: Chart-ready data - histogram bins
ordered: true
--- task
Charting tools need one row per bar. Build the data for a **histogram of monthly spend** with bins
10 wide:

* `bin_start` – the lower edge of the bin: `floor(monthly_spend / 10) * 10`
* `bin_label` – text like `'70-79'`
* `customers` – number of customers in the bin
* `pct` – percentage of all customers, 1 dp

sorted by `bin_start`.
--- starter
SELECT floor(monthly_spend / 10) * 10 AS bin_start, count(*) AS customers
FROM customers
GROUP BY bin_start;
--- solution
SELECT floor(monthly_spend / 10) * 10                                  AS bin_start,
       CAST(bin_start AS INTEGER) || '-' || CAST(bin_start + 9 AS INTEGER) AS bin_label,
       count(*)                                                        AS customers,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1)              AS pct
FROM customers
GROUP BY bin_start
ORDER BY bin_start;
--- hints
- `||` joins text; cast numbers to INTEGER first so you get `70-79`, not `70.0-79.0`.
- `sum(count(*)) OVER ()` is the grand total on every row.
