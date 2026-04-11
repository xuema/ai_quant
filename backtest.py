"""
Simple portfolio backtest.
Takes long/short signals and computes cumulative returns.
"""
import pandas as pd


def backtest(long_df: pd.DataFrame, price_df: pd.DataFrame,
             short_df: pd.DataFrame = None, holding_days: int = 3) -> pd.DataFrame:
    """
    Compute cumulative return of a long-only or long-short portfolio.
    
    Parameters
    ----------
    long_df : DataFrame with ['date', 'code', 'factor', ...]
    price_df : DataFrame with ['code', 'date', 'close'] — all stocks
    short_df : optional DataFrame for short leg (same schema as long_df)
    holding_days : how many days to hold each position

    Returns
    -------
    DataFrame with columns ['date', 'daily_return', 'cumulative_return']
    """

    results = []
    
    # Build a lookup: (code, date) -> close
    price_lookup = price_df.set_index(["code", "date"])["close"]

    for date in sorted(long_df["date"].unique()):
        stocks = long_df[long_df["date"] == date]
        rets = []

        for _, row in stocks.iterrows():
            entry_price = price_lookup.get((str(row["code"]), date))
            if pd.isna(entry_price):
                continue

            exit_date_idx = date + pd.offsets.BDay(holding_days)
            # find the first price on or after exit_date
            future = price_df[
                (price_df["code"] == str(row["code"])) &
                (price_df["date"] >= exit_date)
            ]
            if len(future) > 0:
                exit_price = future.iloc[0]["close"]
                rets.append((exit_price - entry_price) / entry_price)
            else:
                # no exit price available → skip
                pass

        if rets:
            avg_ret = sum(rets) / len(rets)
            results.append({"date": date, "daily_return": avg_ret})

    if not results:
        print("⚠️ backtest: no trades could be evaluated")
        return pd.DataFrame()

    result_df = pd.DataFrame(results)
    result_df["cumulative_return"] = (1 + result_df["daily_return"]).cumprod() - 1
    return result_df
