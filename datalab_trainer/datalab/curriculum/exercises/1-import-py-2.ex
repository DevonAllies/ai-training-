id: import-py-2
stage: import
lang: python
title: Import CSV with dates, JSON and a SQLite database
--- task
Ridgeway's data comes from three systems. Load all three:

1. **`orders`** – `data/orders.csv`, with `order_date` parsed as a real date (datetime64).
2. **`products`** – `data/products.json` as a DataFrame.
3. **`stores`** – the `stores` table from the SQLite database `data/ridgeway.db`
   (use the built-in `sqlite3` module with `pd.read_sql`). Close the connection afterwards.

Finally set **`first_order`** and **`last_order`** to the earliest and latest order dates.
--- starter
import sqlite3
import pandas as pd

orders = pd.read_csv("data/orders.csv")       # TODO parse order_date
products = None                                # TODO
stores = None                                  # TODO

first_order = None
last_order = None
--- solution
import sqlite3
import pandas as pd

orders = pd.read_csv("data/orders.csv", parse_dates=["order_date"])
products = pd.read_json("data/products.json")

con = sqlite3.connect("data/ridgeway.db")
stores = pd.read_sql("SELECT * FROM stores", con)
con.close()

first_order = orders["order_date"].min()
last_order = orders["order_date"].max()
print(orders.dtypes, products, stores, first_order, last_order, sep="\n\n")
--- check
import pandas as pd
expect(len(orders) == 4000, "orders should have 4000 rows.")
expect(pd.api.types.is_datetime64_any_dtype(orders["order_date"]),
       "order_date should be a datetime column. Use parse_dates=['order_date'].")
expect(isinstance(products, pd.DataFrame) and len(products) == 6, "products should be a DataFrame with 6 rows.")
expect(isinstance(stores, pd.DataFrame) and len(stores) == 8 and "city" in stores.columns,
       "stores should be the 8-row `stores` table from data/ridgeway.db.")
expect(pd.Timestamp(first_order) == orders["order_date"].min() and pd.Timestamp(last_order) == orders["order_date"].max(),
       "first_order / last_order should be the min and max of order_date.")
--- hints
- `pd.read_csv(..., parse_dates=["order_date"])`
- `pd.read_json(path)` reads a JSON list of records.
- `con = sqlite3.connect(path)`, then `pd.read_sql("SELECT * FROM stores", con)`.
