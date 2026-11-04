id: clean-r-2
stage: clean
lang: r
title: Numbers, impossible values, dates and booleans in R
--- task
Continue from the de-duplicated data and make these columns correct:

* `income` – numeric without `$` and `,` (`gsub`); fill NA with the **median**.
* `age` – numeric; outside 18–100 → NA; fill NA with the **median of valid ages**, then `floor()` and `as.integer()`.
* `signup_date` – `Date`; try `"%Y-%m-%d"` first, then `"%d/%m/%Y"` for the rest.
* `churned` – integer 1 for yes / y / 1 / true (any case), else 0.

The check compares with the answer key `data/customers.csv`.
--- starter
raw <- read.csv("data/customers_raw.csv", colClasses = "character")
df <- raw[!duplicated(raw$customer_id), ]

# income

# age

# signup_date

# churned

summary(df[, c("income", "age", "churned")])
--- solution
raw <- read.csv("data/customers_raw.csv", colClasses = "character")
df <- raw[!duplicated(raw$customer_id), ]

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

summary(df[, c("income", "age", "churned")])
--- check
ref <- read.csv("data/customers.csv")
d <- df[!duplicated(df$customer_id), ]
m <- match(ref$customer_id, d$customer_id)
expect(!anyNA(m), "df should contain every customer from the answer key.")
d <- d[m, ]
expect(is.numeric(d$income) && !anyNA(d$income), "income should be numeric with no NA.")
expect(max(abs(d$income - ref$income)) < 0.01, "Some income values differ. Remove both $ and , and use the median of the parsed values.")
expect(is.numeric(d$age) && all(d$age == ref$age), "Some ages differ. Set out-of-range ages to NA before taking the median.")
expect(inherits(d$signup_date, "Date"), "signup_date should be a Date.")
expect(!anyNA(d$signup_date) && all(as.character(d$signup_date) == ref$signup_date), "Some signup dates are missing or wrong.")
expect(all(d$churned %in% c(0, 1)) && all(d$churned == ref$churned), "churned should be 0/1 and match the answer key.")
CHECK_MESSAGE <- "All columns match the answer key."
--- hints
- `as.numeric(gsub("[$,]", "", x))` turns "" into NA (with a warning you can suppress).
- Logical indexing: `age[age < 18 | age > 100] <- NA` (guard against NA with `!is.na(age) &`).
- `as.integer(x %in% c("yes", "y", "1", "true"))`
