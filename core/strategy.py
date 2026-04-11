"""
Signal Generation — Long/Short Portfolio

Given dated factor scores, selects top_k stocks for long and bottom_k for short.
If total stocks < 2*top_k, uses percentile-based threshold instead to avoid overlap.
"""
import pandas as pd


def generate_signal(factor_df: pd.DataFrame, top_k: int = 20) -> tuple:
    """
    Generate long/short signals from a factor DataFrame.
    
    - Long = top_k highest factor stocks per day
    - Short = top_k lowest factor stocks per day
    
    When total stocks per day < 2*top_k, uses percentile thresholds
    instead to ensure no overlap between long and short.
    """
    factor_df = factor_df.copy()
    factor_df = factor_df.sort_values(["date", "factor"], ascending=[True, False])

    long_parts = []
    short_parts = []

    for date, group in factor_df.groupby("date"):
        n = len(group)
        # Cap top_k at half the available stocks to prevent overlap
        effective_k = min(top_k, n // 2)
        
        if effective_k == 0:
            continue

        long = group.head(effective_k)
        short = group.tail(effective_k)

        long_parts.append(long)
        short_parts.append(short)

    long = pd.concat(long_parts) if long_parts else pd.DataFrame()
    short = pd.concat(short_parts) if short_parts else pd.DataFrame()

    return long, short
