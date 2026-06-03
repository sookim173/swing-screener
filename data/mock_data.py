"""
data/mock_data.py
Mock data for testing logic without live API.
Replace with real API (yfinance / Polygon / FMP) when running locally.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def make_price_series(start, trend_pct, vol=0.02, days=60):
    """Generate synthetic OHLCV data"""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.today(), periods=days, freq='B')
    close = [start]
    for i in range(1, days):
        daily = trend_pct / days + np.random.normal(0, vol)
        close.append(close[-1] * (1 + daily))
    close = pd.Series(close, index=dates)
    high  = close * (1 + abs(np.random.normal(0, 0.01, days)))
    low   = close * (1 - abs(np.random.normal(0, 0.01, days)))
    open_ = close.shift(1).fillna(close.iloc[0])
    volume_base = 2_000_000
    volume = pd.Series(
        np.random.randint(int(volume_base*0.5), int(volume_base*3), days),
        index=dates
    )
    # Spike volume on last day (ignition signal)
    volume.iloc[-1] = volume_base * 4

    df = pd.DataFrame({
        'open': open_, 'high': high, 'low': low,
        'close': close, 'volume': volume
    })
    return df


MOCK_UNIVERSE = {
    # Ticker: (start_price, 60d_trend, market_cap, float_shares, short_pct)
    "HIMS":  (20.0, 0.25,  4e9,  80e6, 0.18),
    "CELH":  (32.0, 0.18,  3e9,  60e6, 0.12),
    "RKLB":  (18.0, 0.30,  7e9,  40e6, 0.20),
    "IONQ":  (12.0, 0.22,  3e9,  25e6, 0.25),
    "SOFI":  (13.0, 0.12,  13e9, 120e6, 0.08),
    "UPST":  (55.0, 0.15,  5e9,  60e6, 0.22),
    "WOLF":  (8.0, -0.05,  1e9,  90e6, 0.05),   # downtrend — should fail
    "PLUG":  (3.5, -0.10,  2e9,  700e6, 0.15),  # penny zone + heavy float
}


def get_mock_data(ticker: str):
    if ticker not in MOCK_UNIVERSE:
        return None, {}
    start, trend, mktcap, float_sh, short_pct = MOCK_UNIVERSE[ticker]
    df = make_price_series(start, trend)
    info = {
        "market_cap":       mktcap,
        "float_shares":     float_sh,
        "shares_short":     float_sh * short_pct,
        "short_pct_float":  short_pct,
        "avg_volume":       2_000_000,
        "avg_volume_10d":   2_200_000,
        "bid": df["close"].iloc[-1] - 0.01,
        "ask": df["close"].iloc[-1] + 0.01,
        "sector": "Technology",
        "exchange": "NASDAQ",
    }
    return df, info
