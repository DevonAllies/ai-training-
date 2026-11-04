id: basics-r-2
stage: basics
lang: r
title: First steps with data frames in R
--- task
Load `data/customers.csv` into **`df`** and create:

* **`n_customers`** – the number of rows (`nrow`)
* **`premium_north`** – Premium customers in North, columns `customer_id`, `name`, `monthly_spend`,
  sorted by `monthly_spend` from high to low (`order(-x)`)
* a new column **`df$annual_spend`** = monthly_spend × 12
* **`avg_income`** – mean income
--- starter
df <- read.csv("data/customers.csv")
head(df)

n_customers <- NA
premium_north <- NA
avg_income <- NA
--- solution
df <- read.csv("data/customers.csv")
head(df)

n_customers <- nrow(df)
premium_north <- df[df$plan == "Premium" & df$region == "North",
                    c("customer_id", "name", "monthly_spend")]
premium_north <- premium_north[order(-premium_north$monthly_spend), ]
df$annual_spend <- df$monthly_spend * 12
avg_income <- mean(df$income)
print(n_customers); print(head(premium_north)); print(avg_income)
--- check
ref <- read.csv("data/customers.csv")
expect(n_customers == 600, "n_customers should be nrow(df) = 600.")
expect(is.data.frame(premium_north) && identical(names(premium_north), c("customer_id", "name", "monthly_spend")),
       "premium_north should have the columns customer_id, name, monthly_spend.")
expect(nrow(premium_north) == sum(ref$plan == "Premium" & ref$region == "North"), "premium_north should keep only Premium AND North customers.")
expect(!is.unsorted(rev(premium_north$monthly_spend)), "Sort premium_north from the highest monthly_spend to the lowest.")
expect("annual_spend" %in% names(df) && all(df$annual_spend == df$monthly_spend * 12), "Add df$annual_spend.")
expect(abs(avg_income - mean(ref$income)) < 1e-6, "avg_income should be mean(df$income).")
--- hints
- `df[condition, c("col1", "col2")]` filters rows and selects columns.
- `&` combines conditions.
- `x[order(-x$monthly_spend), ]` sorts descending.
