"""Reference ("answer key") cleaning used to build data/customers.csv.

Later stages start from the clean file so a learner who struggles with cleaning
can still do EDA, modelling and reporting.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

REGION_MAP = {"N": "North", "S": "South", "E": "East", "W": "West"}
YES = {"yes", "y", "1", "true"}


def clean_customers(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df = df.drop_duplicates(subset="customer_id", keep="first")
    df["name"] = df["name"].str.strip().str.title()
    email = df["email"].str.strip().str.lower()
    df["email"] = email.where(email.str.contains("@", regex=False), np.nan)
    iso = pd.to_datetime(df["signup_date"], format="%Y-%m-%d", errors="coerce")
    dmy = pd.to_datetime(df["signup_date"], format="%d/%m/%Y", errors="coerce")
    df["signup_date"] = iso.fillna(dmy).dt.strftime("%Y-%m-%d")
    df["region"] = df["region"].str.strip().str.upper().str[0].map(REGION_MAP)
    age = pd.to_numeric(df["age"], errors="coerce")
    age = age.where(age.between(18, 100))
    df["age"] = age.fillna(age.median()).astype(int)
    income = pd.to_numeric(df["income"].str.replace(r"[$,]", "", regex=True), errors="coerce")
    df["income"] = income.fillna(income.median())
    df["plan"] = df["plan"].str.strip().str.title()
    for c in ["monthly_fee", "monthly_spend"]:
        df[c] = pd.to_numeric(df[c])
    for c in ["tenure_months", "support_calls"]:
        df[c] = pd.to_numeric(df[c]).astype(int)
    df["churned"] = df["churned"].str.strip().str.lower().isin(YES).astype(int)
    return df.sort_values("customer_id").reset_index(drop=True)
