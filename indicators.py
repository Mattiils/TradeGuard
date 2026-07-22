"""
indicators.py
Technical analysis indicators used to generate informational trade signals.

Author: Matti

IMPORTANT: These are standard technical indicators (not price predictions).
They describe what has already happened in the price data, not what will
happen next. They are one input among many a trader might consider.
"""

import pandas as pd
import numpy as np


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (0-100). >70 often read as overbought,
    <30 often read as oversold — but this is a convention, not a rule."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val.fillna(50)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD line, signal line, and histogram."""
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range — a volatility measure used here to size
    sensible stop-loss distances rather than guessing a fixed number."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    return true_range.rolling(window=period).mean()


def generate_bias(df: pd.DataFrame) -> dict:
    """
    Combine indicators into a simple, transparent bias label.
    This is NOT a prediction of future price movement — it's a summary
    of current technical conditions, clearly labelled with its reasoning
    so the trader can judge it, not just trust it.
    """
    close = df["Close"]
    sma20 = sma(close, 20).iloc[-1]
    sma50 = sma(close, 50).iloc[-1]
    rsi14 = rsi(close, 14).iloc[-1]
    macd_line, signal_line, hist = macd(close)
    macd_hist_last = hist.iloc[-1]
    last_price = close.iloc[-1]

    reasons = []
    score = 0

    if last_price > sma20 > sma50:
        score += 1
        reasons.append("Price is above both the 20 and 50-period averages (uptrend structure).")
    elif last_price < sma20 < sma50:
        score -= 1
        reasons.append("Price is below both the 20 and 50-period averages (downtrend structure).")
    else:
        reasons.append("Moving averages are mixed — no clear trend structure.")

    if rsi14 > 70:
        reasons.append(f"RSI is {rsi14:.1f} — conventionally read as overbought.")
        score -= 0.5
    elif rsi14 < 30:
        reasons.append(f"RSI is {rsi14:.1f} — conventionally read as oversold.")
        score += 0.5
    else:
        reasons.append(f"RSI is {rsi14:.1f} — neutral range.")

    if macd_hist_last > 0:
        score += 0.5
        reasons.append("MACD histogram is positive (upward momentum).")
    else:
        score -= 0.5
        reasons.append("MACD histogram is negative (downward momentum).")

    if score >= 1:
        bias = "BULLISH bias"
    elif score <= -1:
        bias = "BEARISH bias"
    else:
        bias = "NEUTRAL / mixed signals"

    return {
        "bias": bias,
        "score": score,
        "reasons": reasons,
        "last_price": last_price,
        "rsi": rsi14,
        "sma20": sma20,
        "sma50": sma50,
    }
