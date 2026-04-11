import pandas as pd
import sys
import os

# Allow importing from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import CONFIG


# =========================
# Risk Model Pipeline
# =========================
#
# Correct order:
#   1. Basic cleaning (NaN, fill 6-digit code)
#   2. Extreme value clipping (floor / cap)
#   3. Winsorize (clip by percentile within each date)
#   4. Cross-sectional z-score standardize  ← ONLY here
#
# factor_builder.py already does a raw z-score before calling this,
# so we treat incoming values as raw scores and do the full pipeline.
# The final standardization step produces the output factor.
# =========================

def apply_risk_model(factor_df: pd.DataFrame) -> pd.DataFrame:
    """Apply risk model transformations to the factor DataFrame."""

    df = factor_df.copy()

    # ---- 1. Basic cleaning ----
    df = df.dropna(subset=["factor", "code", "date"])
    df["code"] = df["code"].astype(str).str.zfill(6)

    # ---- 2. Extreme value filtering ----
    floor = CONFIG.get("factor_floor", -10)
    cap = CONFIG.get("factor_cap", 10)
    before_count = len(df)
    df = df[(df["factor"] > floor) & (df["factor"] < cap)]
    if len(df) < before_count:
        print(f"  🧹 RiskModel: removed {before_count - len(df)} extreme values")

    # ---- 3. Winsorize (before standardization) ----
    w_lo = CONFIG.get("winsor_lower", 0.05)
    w_hi = CONFIG.get("winsor_upper", 0.95)

    def winsorize(x):
        return x.clip(x.quantile(w_lo), x.quantile(w_hi))

    df["factor"] = df.groupby("date")["factor"].transform(winsorize)

    # ---- 4. Cross-sectional z-score standardization (final step) ----
    df["factor"] = df.groupby("date")["factor"].transform(
        lambda x: (x - x.mean()) / (x.std() + 1e-6)
    )

    return df
