"""Regenerate the training datasets in datalab/data.

The datasets describe a fictional subscription retailer, "Ridgeway Retail",
plus a bike-rental dataset for the capstone project. The raw files are
deliberately messy (mixed formats, duplicates, typos, impossible values) so the
cleaning lessons have something real to fix.

Run from the datalab_trainer folder:   python tools/make_datasets.py
The output is deterministic (fixed seed), so re-running gives identical files.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from datalab.reference import clean_customers  # noqa: E402

DATA = ROOT / "datalab" / "data"
rng = np.random.default_rng(42)

FIRST = ["James", "Mary", "Thabo", "Aisha", "Liam", "Olivia", "Sipho", "Emma", "Noah", "Zanele",
         "Lucas", "Mia", "Pieter", "Ava", "Ethan", "Lerato", "Mason", "Sofia", "Kagiso", "Isla",
         "Arjun", "Chloe", "Daniel", "Naledi", "Jack", "Grace", "Ruan", "Amara", "Leo", "Hannah"]
LAST = ["Smith", "Naidoo", "Dlamini", "van der Merwe", "Jones", "Botha", "Khumalo", "Brown",
        "Patel", "Williams", "Mokoena", "Taylor", "Pillay", "Nkosi", "Wilson", "Jacobs",
        "Mahlangu", "Davies", "Fourie", "Evans"]
REGIONS = ["North", "South", "East", "West"]
PLANS = ["Basic", "Standard", "Premium"]
FEES = {"Basic": 19.99, "Standard": 39.99, "Premium": 69.99}


def messy_case(s: str) -> str:
    r = rng.random()
    if r < 0.15:
        return s.lower()
    if r < 0.25:
        return s.upper()
    if r < 0.35:
        return "  " + s + " "
    return s


def make_customers(n: int = 600) -> pd.DataFrame:
    ids = [f"C{i:04d}" for i in range(1, n + 1)]
    first = rng.choice(FIRST, n)
    last = rng.choice(LAST, n)
    region = rng.choice(REGIONS, n, p=[0.3, 0.25, 0.25, 0.2])
    plan = rng.choice(PLANS, n, p=[0.45, 0.35, 0.2])
    age = np.clip(rng.normal(41, 12, n).round(), 18, 80).astype(int)
    income = np.round(np.exp(rng.normal(np.log(58000), 0.4, n)), -2)
    tenure = rng.integers(1, 61, n)
    calls = rng.poisson(1.2 + 0.8 * (plan == "Basic"), n)
    plan_spend = np.select([plan == "Basic", plan == "Standard"], [0, 12], 30)
    spend = np.round(18 + 0.00055 * income + plan_spend + 0.25 * age + rng.normal(0, 6, n), 2)
    plan_churn = np.select([plan == "Basic", plan == "Standard"], [0.35, 0.0], -0.7)
    logit = -0.9 - 0.065 * tenure + 0.6 * calls + plan_churn
    churn = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    start = pd.Timestamp("2021-01-01")
    signup = start + pd.to_timedelta(rng.integers(0, 1277, n), unit="D")

    rows = []
    for i in range(n):
        name = f"{first[i]} {last[i]}"
        email = f"{first[i]}.{last[i]}".lower().replace(" ", "") + "@example.com"
        r = rng.random()
        if r < 0.03:
            email = email.replace("@", "")
        elif r < 0.05:
            email = ""
        # dates: mostly ISO, some day/month/year
        d = signup[i]
        date_s = d.strftime("%Y-%m-%d") if rng.random() < 0.7 else d.strftime("%d/%m/%Y")
        # region variants
        reg = region[i]
        rr = rng.random()
        if rr < 0.08:
            reg = reg[0]
        elif rr < 0.12:
            reg = reg[0] + "."
        else:
            reg = messy_case(reg)
        # age: missing / impossible
        ra = rng.random()
        age_s: object = int(age[i])
        if ra < 0.04:
            age_s = ""
        elif ra < 0.055:
            age_s = int(rng.choice([-1, 0, 999, 150]))
        # income: "$52,000", "52000" or missing
        ri = rng.random()
        if ri < 0.05:
            inc_s = ""
        elif ri < 0.6:
            inc_s = f"${income[i]:,.0f}"
        else:
            inc_s = f"{income[i]:.0f}"
        churn_s = {1: ["Yes", "Y", "1", "yes", "TRUE"], 0: ["No", "N", "0", "no", "FALSE"]}[churn[i]]
        churn_s = rng.choice(churn_s, p=[0.6, 0.1, 0.15, 0.1, 0.05])
        rows.append({
            "customer_id": ids[i],
            "name": messy_case(name),
            "email": email,
            "signup_date": date_s,
            "region": reg,
            "age": age_s,
            "income": inc_s,
            "plan": messy_case(plan[i]).strip() if rng.random() < 0.5 else plan[i],
            "monthly_fee": FEES[plan[i]],
            "tenure_months": int(tenure[i]),
            "support_calls": int(calls[i]),
            "monthly_spend": spend[i],
            "churned": churn_s,
        })
    df = pd.DataFrame(rows)
    dups = df.sample(18, random_state=7)
    df = pd.concat([df, dups]).sample(frac=1, random_state=3).reset_index(drop=True)
    return df


CATEGORIES = [
    {"category": "Electronics", "department": "Tech", "margin": 0.18, "avg_price": 240},
    {"category": "Books", "department": "Media", "margin": 0.32, "avg_price": 22},
    {"category": "Garden", "department": "Home", "margin": 0.27, "avg_price": 55},
    {"category": "Kitchen", "department": "Home", "margin": 0.30, "avg_price": 48},
    {"category": "Sports", "department": "Leisure", "margin": 0.25, "avg_price": 70},
    {"category": "Toys", "department": "Leisure", "margin": 0.35, "avg_price": 30},
]


def make_orders(clean: pd.DataFrame, n: int = 4000) -> pd.DataFrame:
    cust = clean.sample(n, replace=True, random_state=11, weights=clean["monthly_spend"])
    cats = rng.choice(len(CATEGORIES), n, p=[0.12, 0.25, 0.13, 0.2, 0.15, 0.15])
    end = pd.Timestamp("2024-12-31")
    rows = []
    for i, (_, c) in enumerate(cust.iterrows()):
        s = pd.Timestamp(c["signup_date"])
        span = max((end - s).days, 1)
        d = s + pd.Timedelta(days=int(rng.integers(0, span)))
        cat = CATEGORIES[cats[i]]
        price = round(float(cat["avg_price"] * np.exp(rng.normal(0, 0.35))), 2)
        rows.append({
            "order_id": 100001 + i,
            "customer_id": c["customer_id"],
            "order_date": d.strftime("%Y-%m-%d"),
            "category": cat["category"],
            "quantity": int(rng.integers(1, 6) if cat["avg_price"] < 100 else rng.integers(1, 3)),
            "unit_price": price,
            "discount": float(rng.choice([0, 0, 0, 0.1, 0.2])),
        })
    return pd.DataFrame(rows).sort_values(["order_date", "order_id"]).reset_index(drop=True)


def make_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE stores (store_id INTEGER PRIMARY KEY, region TEXT, city TEXT, opened TEXT, floor_m2 INTEGER)")
    stores = [
        (1, "North", "Polokwane", "2015-03-01", 820), (2, "North", "Pretoria", "2012-07-15", 1400),
        (3, "South", "Cape Town", "2010-01-20", 1650), (4, "South", "George", "2019-09-01", 600),
        (5, "East", "Durban", "2011-05-05", 1300), (6, "East", "Richards Bay", "2020-02-14", 540),
        (7, "West", "Upington", "2018-11-30", 480), (8, "West", "Springbok", "2021-06-01", 350),
    ]
    con.executemany("INSERT INTO stores VALUES (?,?,?,?,?)", stores)
    con.execute("CREATE TABLE targets (region TEXT, year INTEGER, revenue_target REAL)")
    tg = [(r, y, t) for r, base in zip(REGIONS, [210000, 180000, 170000, 120000])
          for y, t in [(2023, base), (2024, base * 1.1)]]
    con.executemany("INSERT INTO targets VALUES (?,?,?)", tg)
    con.commit()
    con.close()


def make_rentals() -> pd.DataFrame:
    days = pd.date_range("2023-01-01", "2024-12-30", freq="D")
    n = len(days)
    doy = days.dayofyear.values
    # Southern-hemisphere seasons: hot in Jan, cold in Jul
    temp = 18 + 8 * np.cos(2 * np.pi * (doy - 15) / 365) + rng.normal(0, 3, n)
    hum = np.clip(60 - 0.8 * (temp - 18) + rng.normal(0, 12, n), 15, 100)
    wind = np.clip(rng.gamma(3, 4, n), 0, 60)
    weather = rng.choice(["Clear", "Mist", "Rain"], n, p=[0.6, 0.25, 0.15])
    weekend = days.dayofweek.values >= 5
    holiday = rng.random(n) < 0.03
    trend = np.arange(n) * 0.9
    rentals = (900 + 75 * temp - 6 * hum - 9 * wind + trend
               + np.select([weather == "Mist", weather == "Rain"], [-150, -550], 0)
               + 220 * weekend + 120 * holiday + rng.normal(0, 140, n))
    rentals = np.clip(rentals, 20, None).round().astype(int)
    season = np.select([np.isin(days.month, [12, 1, 2]), np.isin(days.month, [3, 4, 5]),
                        np.isin(days.month, [6, 7, 8])], ["Summer", "Autumn", "Winter"], "Spring")
    df = pd.DataFrame({
        "date": days.strftime("%Y-%m-%d"),
        "season": season,
        "holiday": holiday.astype(int),
        "weather": [messy_case(w).strip() if rng.random() < 0.3 else w for w in weather],
        "temp_c": temp.round(1).astype(object),
        "humidity": [f"{h:.0f}%" for h in hum],
        "windspeed_kmh": wind.round(1),
        "rentals": rentals,
    })
    miss = rng.random(n)
    df.loc[miss < 0.03, "temp_c"] = ""
    df.loc[(miss >= 0.03) & (miss < 0.04), "temp_c"] = -99.0  # sensor error code
    dups = df.sample(6, random_state=5)
    return pd.concat([df, dups]).sort_values("date", kind="stable").reset_index(drop=True)


def make_store_sales() -> pd.DataFrame:
    """Weekly sales 2021-2024 for the forecasting module: trend + yearly season + noise."""
    r = np.random.default_rng(2024)  # own generator so other files don't change
    weeks = pd.date_range("2021-01-04", "2024-12-30", freq="W-MON")
    t = np.arange(len(weeks))
    woy = weeks.isocalendar().week.values.astype(float)
    season = 9000 * np.cos(2 * np.pi * (woy - 51) / 52)        # December peak
    promo = (r.random(len(weeks)) < 0.08).astype(int)
    sales = 42000 + 140 * t + season + 6500 * promo + r.normal(0, 2500, len(weeks))
    return pd.DataFrame({"week": weeks.strftime("%Y-%m-%d"), "sales": sales.round(0).astype(int),
                         "promo": promo})


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    raw = make_customers()
    raw.to_csv(DATA / "customers_raw.csv", index=False)
    clean = clean_customers(pd.read_csv(DATA / "customers_raw.csv", dtype=str, keep_default_na=False))
    clean.to_csv(DATA / "customers.csv", index=False)
    orders = make_orders(clean)
    orders.to_csv(DATA / "orders.csv", index=False)
    (DATA / "products.json").write_text(json.dumps(CATEGORIES, indent=2) + "\n", encoding="utf-8")
    make_db(DATA / "ridgeway.db")
    make_rentals().to_csv(DATA / "rentals_raw.csv", index=False)
    make_store_sales().to_csv(DATA / "store_sales.csv", index=False)
    print(f"customers_raw {len(raw)} rows, customers {len(clean)} rows, orders {len(orders)} rows")
    print(f"churn rate {clean['churned'].mean():.3f}")


if __name__ == "__main__":
    main()
