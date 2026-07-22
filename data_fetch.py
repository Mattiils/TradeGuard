"""
data_fetch.py
Pulls historical/live price data for a symbol.

Author: Matti

Uses yfinance (free, no API key) for stocks, ETFs, indices, and most
crypto pairs (e.g. "BTC-USD", "ETH-USD"). Falls back to synthetic demo
data if there's no internet connection, so the tool is still runnable
for testing/demoing offline.
"""

import numpy as np
import pandas as pd


def fetch_price_data(symbol: str, period: str = "3mo", interval: str = "1d") -> pd.DataFrame:
    """
    Fetch OHLC price data for `symbol`.
    period examples: '1mo', '3mo', '6mo', '1y'
    interval examples: '1d', '1h', '15m' (intraday ranges are limited by Yahoo)
    """
    try:
        import yfinance as yf
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        if df is None or df.empty:
            raise ValueError("No data returned")
        # yfinance sometimes returns MultiIndex columns for single tickers
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        print(f"[!] Live data fetch failed ({e}). Using demo/synthetic data instead.")
        return _generate_demo_data(symbol)


def _generate_demo_data(symbol: str, days: int = 120) -> pd.DataFrame:
    """Synthetic random-walk price series so the tool works offline for demos/tests."""
    rng = np.random.default_rng(abs(hash(symbol)) % (2**32))
    price = 100.0
    rows = []
    dates = pd.date_range(end=pd.Timestamp.today(), periods=days, freq="D")

    for date in dates:
        change_pct = rng.normal(0, 0.015)
        open_p = price
        close_p = open_p * (1 + change_pct)
        high_p = max(open_p, close_p) * (1 + abs(rng.normal(0, 0.005)))
        low_p = min(open_p, close_p) * (1 - abs(rng.normal(0, 0.005)))
        volume = int(rng.uniform(1_000_000, 5_000_000))
        rows.append([date, open_p, high_p, low_p, close_p, volume])
        price = close_p

    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df.set_index("Date", inplace=True)
    return df
