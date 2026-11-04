id: clean-r-1
stage: clean
lang: r
title: Duplicates, whitespace and labels in base R
--- task
Starting from the raw character data, build **`df`** with:

1. one row per `customer_id` (`duplicated()`),
2. `name` trimmed (`trimws`) and starting with a capital letter (e.g. `tools::toTitleCase(tolower(x))`),
3. `region` mapped to `North` / `South` / `East` / `West`,
4. `plan` mapped to `Basic` / `Standard` / `Premium`.
--- starter
raw <- read.csv("data/customers_raw.csv", colClasses = "character")
print(table(raw$region))

df <- raw
# 1. remove duplicated customer_id rows
# 2. tidy name
# 3. region: first letter of trimws(toupper(region)) -> name
# 4. plan

print(table(df$region))
--- solution
raw <- read.csv("data/customers_raw.csv", colClasses = "character")
print(table(raw$region))

df <- raw[!duplicated(raw$customer_id), ]
df$name <- tools::toTitleCase(tolower(trimws(df$name)))
region_map <- c(N = "North", S = "South", E = "East", W = "West")
df$region <- unname(region_map[substr(toupper(trimws(df$region)), 1, 1)])
p <- tolower(trimws(df$plan))
df$plan <- paste0(toupper(substr(p, 1, 1)), substring(p, 2))

print(table(df$region))
print(table(df$plan))
--- check
expect(nrow(df) == 600, paste("df should have 600 rows, it has", nrow(df)))
expect(!anyDuplicated(df$customer_id), "customer_id should be unique.")
expect(all(df$name == trimws(df$name)), "Some names still have leading or trailing spaces: use trimws().")
expect(all(grepl("^[A-Z]", df$name)) && !any(df$name == toupper(df$name)), "Names should start with a capital and not be ALL CAPS.")
expect(all(df$region %in% c("North", "South", "East", "West")), "region should only be North, South, East or West.")
expect(setequal(unique(df$plan), c("Basic", "Standard", "Premium")), "plan should only be Basic, Standard or Premium.")
--- hints
- `df <- raw[!duplicated(raw$customer_id), ]`
- A named vector works as a lookup table: `c(N = "North", ...)[letters]`. Wrap in `unname()`.
- `substr(x, 1, 1)` is the first character.
