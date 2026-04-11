"""
Simple CAR calculation (legacy, kept for compatibility).

Use event_study_extended.calc_event_car for the full pre/post window breakdown.
"""
import pandas as pd


def calc_return(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").copy()
    df["ret"] = df["close"].pct_change()
    return df


def calc_car(
    stock_df: pd.DataFrame,
    event_date: str,
    window: int = 3,
    market_df: pd.DataFrame = None
) -> float:
    """
    Calculate CAR over `window` trading days starting from the event date.
    If market_df is provided, returns excess CAR (stock return minus market return).
    """
    stock_df = calc_return(stock_df)

    event_date = pd.to_datetime(event_date)

    # Find event index (first row with date >= event_date)
    match = stock_df[stock_df["date"] == event_date]
    if len(match) > 0:
        idx = match.index[0]
    else:
        future = stock_df[stock_df["date"] > event_date]
        if len(future) == 0:
            return 0.0
        idx = future.index[0]

    if market_df is None:
        window_df = stock_df.iloc[idx: idx + window]
        if len(window_df) < window:
            return 0.0
        return round(window_df["ret"].sum(), 6)

    # Market-adjusted CAR
    market_df = calc_return(market_df).rename(columns={"close": "mkt_close", "ret": "ret_mkt"})
    df = stock_df.merge(market_df[["date", "ret_mkt"]], on="date", how="left")

    window_df = df.iloc[idx: idx + window]
    if len(window_df) < window:
        return 0.0

    df["ar"] = df["ret"] - df["ret_mkt"]

    return round(window_df["ar"].sum(), 6)
