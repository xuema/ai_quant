import pandas as pd
import numpy as np


# =========================
# 1️⃣ Returns
# =========================
def calc_return(df: pd.DataFrame) -> pd.DataFrame:
    """Add a 'ret' column (simple returns)."""
    df = df.sort_values("date").copy()
    df["ret"] = df["close"].pct_change()
    return df


# =========================
# 2️⃣ Main CAR function (full event decomposition)
# =========================
#
# Timeline (trading days) — 公告当天可买：
#
# |--pre_window--| EVENT(当天买入) | post_window |
#   -5  -4  -3  -2        0            +1  +2  +3
#
# event_date   = 公告发布日期（视为当天可买入）
#
# car_pre  = 事件日前 pre_window 个交易日（不含事件日）→ 泄露检测
# car_post = 从事件日当天起（含当天！）到 +post_window → 实际可获得的收益
# car_total = car_pre + car_post
# leakage  = car_pre / car_total  (> 0.5 表示公告前已提前反应 → 消息泄露)
# =========================

def calc_event_car(
    stock_df: pd.DataFrame,
    event_date: str,
    market_df: pd.DataFrame = None,
    pre_window: int = 5,
    post_window: int = 3
) -> dict:
    """
    Calculate Cumulative Abnormal Return (CAR) around a single event.

    Parameters
    ----------
    stock_df : DataFrame with columns ['date', 'close', ...]
    event_date : str or datetime (announcement date)
    market_df : optional DataFrame with ['date', 'mkt_close' / 'close']
    pre_window : number of trading days before and including the event
    post_window : number of trading days after the event

    Returns
    -------
    dict with car_pre, car_post, car_total, leakage_ratio
    or None if insufficient data.
    """

    event_date = pd.to_datetime(event_date)

    # --- Add returns ---
    stock_df = calc_return(stock_df)

    use_market = market_df is not None
    if use_market:
        market_df = calc_return(market_df)
        market_df = market_df.rename(
            columns={"close": "mkt_close", "ret": "ret_mkt"}
        )
        df = stock_df.merge(market_df[["date", "ret_mkt"]], on="date", how="left")
    else:
        df = stock_df.copy()

    df = df.sort_values("date").reset_index(drop=True)

    # --- Find event index (first row where date >= event_date) ---
    match = df[df["date"] == event_date]
    if len(match) > 0:
        event_idx = match.index[0]
    else:
        # Event date not in data → find first trading day after
        future = df[df["date"] > event_date]
        if len(future) == 0:
            return None
        event_idx = future.index[0]

    # --- Define windows ---
    # car_pre: 不含事件日，只看事件日前 N 个交易日（纯泄露检测）
    # car_post: 从事件日当天开始（含当天！）→ 真正可获得的收益
    pre_start = max(0, event_idx - pre_window)
    pre_end = event_idx - 1  # 不含事件日

    post_start = event_idx    # 从事件日当天开始（含当天）
    post_end = min(len(df), post_start + post_window)

    # --- Calculate CAR ---
    if use_market:
        df["ar"] = df["ret"] - df["ret_mkt"]

        car_pre = df.iloc[pre_start:pre_end + 1]["ar"].sum()
        car_post = df.iloc[post_start:post_end]["ar"].sum() if post_start < post_end else 0.0
    else:
        car_pre = df.iloc[pre_start:pre_end + 1]["ret"].sum()
        car_post = df.iloc[post_start:post_end]["ret"].sum() if post_start < post_end else 0.0

    car_total = car_pre + car_post

    # --- Leakage ratio ---
    leakage = None
    if car_total is not None and abs(car_total) > 1e-8:
        leakage = car_pre / (car_pre + car_post)

    return {
        "car_pre": round(car_pre, 6),
        "car_post": round(car_post, 6),
        "car_total": round(car_total, 6),
        "leakage_ratio": round(leakage, 4) if leakage is not None else None
    }
