"""
Factor Builder — from raw announcement scores to a cross-sectional factor.

Pipeline:
  1. Aggregate scores per (code, date)
  2. Volatility adjustment (score std per stock, to prevent large-cap bias)
  3. Return factor = score / vol  → raw score
  NO standardization here — risk_model.py handles z-score + winsorize.
"""
import pandas as pd
import numpy as np


def build_factor(df: pd.DataFrame) -> pd.DataFrame:
    """Build raw announcement factor from aggregated scores."""

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["score"] = pd.to_numeric(df["score"], errors="coerce")

    # 1. Aggregate: sum scores per (code, date)
    base = df.groupby(["code", "date"])["score"].sum().reset_index()

    # 保留每组的元数据列（取第一条非空）
    for col in ["reason", "name", "event_type", "confidence", "label", "holding_days"]:
        if col not in df.columns:
            continue
        if col in ("confidence", "holding_days"):
            # Numeric: use max
            vals = df.groupby(["code", "date"])[col].max().reset_index()
        else:
            # Text: use first non-empty
            vals = df[df[col].notna() & (df[col] != "")].groupby(
                ["code", "date"]
            )[col].first().reset_index()
        base = base.merge(vals, on=["code", "date"], how="left")

    # 2. Volatility adjustment (per-stock std of raw scores)
    vol = df.groupby("code")["score"].std().reset_index()
    vol.columns = ["code", "vol"]
    base = base.merge(vol, on="code", how="left")
    base["vol"] = base["vol"].fillna(1)

    # 3. Raw factor = score / vol
    base["factor"] = base["score"] / base["vol"]

    return base
