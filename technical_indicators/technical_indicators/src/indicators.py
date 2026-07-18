"""
Pure-Python technical indicator implementations.

Each function takes numpy arrays (or pandas Series) of OHLC prices and returns
a numpy array with the same length as the input, padded with NaN where the
indicator is undefined.
"""

import numpy as np


def _ema(x, span):
    """Exponential moving average using Wilder's smoothing (α = 1/span)."""
    alpha = 1.0 / span
    out = np.full_like(x, np.nan, dtype=float)
    if len(x) < span:
        return out
    # Seed with SMA of first `span` values
    out[span - 1] = np.nanmean(x[:span])
    for i in range(span, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


# ── RSI ─────────────────────────────────────────────────────────────────────
def rsi(close, period: int = 14) -> np.ndarray:
    """Relative Strength Index (Wilder, 1978)."""
    close = np.asarray(close, dtype=float)
    delta = np.diff(close, prepend=np.nan)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = _ema(gain, period)
    avg_loss = _ema(loss, period)
    rs = avg_gain / np.where(avg_loss != 0, avg_loss, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


# ── MACD ────────────────────────────────────────────────────────────────────
def macd(close, fast: int = 12, slow: int = 26, signal: int = 9):
    """Moving Average Convergence Divergence. Returns (DIF, DEA, MACD_hist)."""
    close = np.asarray(close, dtype=float)
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    dif = ema_fast - ema_slow
    dea = _ema(dif, signal)
    hist = 2.0 * (dif - dea)  # Chinese convention
    return dif, dea, hist


# ─ Bollinger Bands ─────────────────────────────────────────────────────────
def bollinger_bands(close, period: int = 20, num_std: float = 2.0):
    """Returns (upper, middle, lower)."""
    close = np.asarray(close, dtype=float)
    ma = _simple_ma(close, period)
    std = _rolling_std(close, period)
    return ma + num_std * std, ma, ma - num_std * std


def _simple_ma(x, n):
    x = np.asarray(x, dtype=float)
    out = np.full_like(x, np.nan, dtype=float)
    cum = np.cumsum(x)
    out[n - 1:] = (cum[n - 1:] - np.concatenate(([0], cum[:-n]))) / n
    return out


def _rolling_std(x, n):
    x = np.asarray(x, dtype=float)
    out = np.full_like(x, np.nan, dtype=float)
    for i in range(n - 1, len(x)):
        out[i] = np.std(x[i - n + 1: i + 1], ddof=0)
    return out


# ── Williams %R ─────────────────────────────────────────────────────────────
def williams_r(high, low, close, period: int = 14) -> np.ndarray:
    """Williams %R oscillator."""
    high, low, close = (np.asarray(a, dtype=float) for a in (high, low, close))
    highest = np.full_like(high, np.nan)
    lowest  = np.full_like(low,  np.nan)
    for i in range(period - 1, len(high)):
        highest[i] = np.max(high[i - period + 1: i + 1])
        lowest[i]  = np.min(low[i - period + 1: i + 1])
    denom = highest - lowest
    wr = -100.0 * (highest - close) / np.where(denom != 0, denom, np.nan)
    return wr


# ── ATR ─────────────────────────────────────────────────────────────────────
def atr(high, low, close_prev, period: int = 14, mode: str = "sma") -> np.ndarray:
    """
    Average True Range.
    mode='sma'  → simple moving average of TR (default).
    mode='wema' → Wilder's exponential smoothing.
    `close_prev` is the prior-session close; first element can be NaN/High.
    """
    high, low, cp = (np.asarray(a, dtype=float) for a in (high, low, close_prev))
    tr = np.maximum(high - low,
                    np.maximum(np.abs(high - cp), np.abs(low - cp)))
    out = _ema(tr, period) if mode == "wema" else _simple_ma(tr, period)
    return out


# ─ CR 能量指标 ───────────────────────────────────────────────────────────────
def cr(high, low, close, prev_high, prev_low, prev_close, period: int = 26) -> np.ndarray:
    """
    CR (Energy Index / 人气意愿指标).
    CR = sum(max(H_t - PM_{t-1}, 0)) / sum(max(PM_{t-1} - L_t, 0)) * 100
    where PM_{t-1} = (prev_high + prev_low + prev_close) / 3
    Returns CR and the MA lines of CR (5, 10, 20, 60).
    """
    high, low, close = (np.asarray(a, dtype=float) for a in (high, low, close))
    pm = (prev_high + prev_low + prev_close) / 3.0
    bull = np.maximum(high - pm, 0.0)
    bear = np.maximum(pm - low, 0.0)
    bull_cum = np.cumsum(bull)
    bear_cum = np.cumsum(bear)
    cr_val = np.full_like(high, np.nan)
    for i in range(period - 1, len(high)):
        b = bull_cum[i] - bull_cum[i - period] if i > period - 1 else bull_cum[i]
        s = bear_cum[i] - bear_cum[i - period] if i > period - 1 else bear_cum[i]
        cr_val[i] = 100.0 * b / s if s != 0 else 100.0
    # MA lines
    ma5  = _simple_ma(cr_val, 5)
    ma10 = _simple_ma(cr_val, 10)
    ma20 = _simple_ma(cr_val, 20)
    ma60 = _simple_ma(cr_val, 60)
    return cr_val, ma5, ma10, ma20, ma60
