id: clean-r-3
stage: clean
lang: r
title: A reusable, validated cleaning function in R
level: 2
--- task
Combine your R cleaning steps into a function **`clean_customers(raw)`** that returns the clean data frame,
ending with **`stopifnot()`** checks (unique ids, allowed regions and plans, ages 18–100, no NA income).

Then create **`clean <- clean_customers(raw)`** and save it with
`write.csv(clean, "data/my_customers_r.csv", row.names = FALSE)`.

The check compares `region, age, income, plan, signup_date, churned` with the answer key.
--- starter
raw <- read.csv("data/customers_raw.csv", colClasses = "character")

clean_customers <- function(raw) {
  df <- raw
  # ... your steps from clean-r-1 and clean-r-2 ...
  df
}

clean <- clean_customers(raw)
write.csv(clean, "data/my_customers_r.csv", row.names = FALSE)
--- solution
raw <- read.csv("data/customers_raw.csv", colClasses = "character")

clean_customers <- function(raw) {
  df <- raw[!duplicated(raw$customer_id), ]
  df$name <- tools::toTitleCase(tolower(trimws(df$name)))
  region_map <- c(N = "North", S = "South", E = "East", W = "West")
  df$region <- unname(region_map[substr(toupper(trimws(df$region)), 1, 1)])
  p <- tolower(trimws(df$plan))
  df$plan <- paste0(toupper(substr(p, 1, 1)), substring(p, 2))

  income <- suppressWarnings(as.numeric(gsub("[$,]", "", df$income)))
  income[is.na(income)] <- median(income, na.rm = TRUE)
  df$income <- income
  age <- suppressWarnings(as.numeric(df$age))
  age[!is.na(age) & (age < 18 | age > 100)] <- NA
  age[is.na(age)] <- median(age, na.rm = TRUE)
  df$age <- as.integer(floor(age))

  d <- as.Date(df$signup_date, format = "%Y-%m-%d")
  d[is.na(d)] <- as.Date(df$signup_date[is.na(d)], format = "%d/%m/%Y")
  df$signup_date <- d
  df$churned <- as.integer(tolower(trimws(df$churned)) %in% c("yes", "y", "1", "true"))
  for (col in c("monthly_fee", "monthly_spend")) df[[col]] <- as.numeric(df[[col]])
  for (col in c("tenure_months", "support_calls")) df[[col]] <- as.integer(df[[col]])

  stopifnot(!anyDuplicated(df$customer_id),
            all(df$region %in% region_map),
            all(df$plan %in% c("Basic", "Standard", "Premium")),
            all(df$age >= 18 & df$age <= 100),
            !anyNA(df$income), !anyNA(df$signup_date))
  df[order(df$customer_id), ]
}

clean <- clean_customers(raw)
write.csv(clean, "data/my_customers_r.csv", row.names = FALSE)
str(clean)
--- check
expect(is.function(clean_customers), "Define clean_customers(raw).")
expect(file.exists("data/my_customers_r.csv"), "Save the result to data/my_customers_r.csv.")
expect(any(grepl("stopifnot", deparse(body(clean_customers)))), "Validate inside the function with stopifnot().")
ref <- read.csv("data/customers.csv")
m <- match(ref$customer_id, clean$customer_id)
expect(nrow(clean) == 600 && !anyNA(m), "clean should contain exactly the 600 customers.")
c2 <- clean[m, ]
for (col in c("region", "plan", "churned", "age"))
  expect(all(as.character(c2[[col]]) == as.character(ref[[col]])), paste("Column", col, "differs from the answer key."))
expect(max(abs(c2$income - ref$income)) < 0.01, "Column income differs from the answer key.")
expect(all(as.character(c2$signup_date) == ref$signup_date), "Column signup_date differs from the answer key.")
--- hints
- Copy your working code from clean-r-1 and clean-r-2 into the function body.
- `stopifnot(cond1, cond2, ...)` stops with an error if any condition is FALSE.
