"""
modules/indicators.py
Calculate all technical indicators from OHLCV DataFrame
"""

import pandas as pd
import numpy as np


def calculate_indicators(df: pd.DataFrame) -> dict:
    close = df["close"]
    volume = df["volume"]
    high = df["high"]
    low = df["low"]

    # ── Moving Averages ──────────────────────────────────────
    ma8   = close.ewm(span=8, adjust=False).mean()
    ma20  = close.rolling(20).mean()
    ma50  = close.rolling(50).mean()

    # ── Returns ──────────────────────────────────────────────
    ret_1d  = close.pct_change(1).iloc[-1]
    ret_5d  = (close.iloc[-1] / close.iloc[-6] - 1) if len(close) >= 6 else 0
    ret_20d = (close.iloc[-1] / close.iloc[-21] - 1) if len(close) >= 21 else 0

    # ── Volume ───────────────────────────────────────────────
    avg_vol_20 = volume.rolling(20).mean().iloc[-1]
    today_vol  = volume.iloc[-1]
    rvol       = today_vol / avg_vol_20 if avg_vol_20 > 0 else 0

    # RVOL 3/5-day average: smoothed momentum signal vs single-day spike
    rvol_series  = volume / volume.rolling(20).mean()
    rvol_3d_avg  = rvol_series.iloc[-3:].mean() if len(rvol_series) >= 3 else rvol
    rvol_5d_avg  = rvol_series.iloc[-5:].mean() if len(rvol_series) >= 5 else rvol

    avg_dollar_vol = (close * volume).rolling(20).mean().iloc[-1]

    # ── 52-week high ─────────────────────────────────────────
    high_52w = high.rolling(252).max().iloc[-1] if len(high) >= 252 else high.max()
    pct_from_52w_high = close.iloc[-1] / high_52w - 1

    # ── VWAP proxy (volume-weighted MA over 20 days) ─────────
    # Note: true VWAP requires intraday data; this is a daily approximation
    typical_price = (high + low + close) / 3
    vwap = (typical_price * volume).rolling(20).sum() / volume.rolling(20).sum()
    above_vwap = close.iloc[-1] > vwap.iloc[-1]

    # ── ATR (14-day) ─────────────────────────────────────────
    high_low   = high - low
    high_close = (high - close.shift()).abs()
    low_close  = (low  - close.shift()).abs()
    tr  = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr_val = tr.rolling(14).mean().iloc[-1]
    atr = float(atr_val) if not pd.isna(atr_val) else float(close.iloc[-1] * 0.03)

    # ── Trend flags ──────────────────────────────────────────
    above_ma20 = close.iloc[-1] > ma20.iloc[-1]
    above_ma50 = close.iloc[-1] > ma50.iloc[-1]
    ma20_rising = ma20.iloc[-1] > ma20.iloc[-5] if len(ma20) >= 5 else False

    # ── Pullback detection ───────────────────────────────────
    # Last 3 days: is current price pulling back from recent high?
    recent_high = high.iloc[-10:-1].max() if len(high) >= 10 else high.max()
    pullback_pct = close.iloc[-1] / recent_high - 1  # negative = pullback

    # Volume during pullback (last 2 days vs spike day)
    vol_during_pullback = volume.iloc[-2:].mean()
    vol_on_spike = volume.iloc[-10:-2].max() if len(volume) >= 10 else volume.mean()
    pullback_vol_shrinking = vol_during_pullback < vol_on_spike * 0.7

    # Higher low check
    lows_5d = low.iloc[-5:]
    higher_low = lows_5d.iloc[-1] > lows_5d.iloc[0] if len(lows_5d) >= 2 else False

    # ── Breakout detection ───────────────────────────────────
    prior_high_20d = high.iloc[-22:-2].max() if len(high) >= 22 else high.max()
    breakout_today = close.iloc[-1] > prior_high_20d
    near_breakout = close.iloc[-1] >= prior_high_20d * 0.98

    return {
        # Price
        "close": round(close.iloc[-1], 2),
        "open": round(df["open"].iloc[-1], 2),

        # MAs
        "ma8": round(ma8.iloc[-1], 2),
        "ma20": round(ma20.iloc[-1], 2),
        "ma50": round(ma50.iloc[-1], 2) if not pd.isna(ma50.iloc[-1]) else None,

        # Returns
        "ret_1d": round(ret_1d, 4),
        "ret_5d": round(ret_5d, 4),
        "ret_20d": round(ret_20d, 4),

        # Volume
        "rvol":         round(rvol, 2),
        "rvol_3d_avg":  round(float(rvol_3d_avg), 2) if not pd.isna(rvol_3d_avg) else round(rvol, 2),
        "rvol_5d_avg":  round(float(rvol_5d_avg), 2) if not pd.isna(rvol_5d_avg) else round(rvol, 2),
        "avg_vol_20":   int(avg_vol_20),
        "today_vol":    int(today_vol),
        "avg_dollar_vol": round(avg_dollar_vol, 0),

        # Trend
        "above_ma20": above_ma20,
        "above_ma50": above_ma50,
        "ma20_rising": ma20_rising,
        "above_vwap": above_vwap,
        "pct_from_52w_high": round(pct_from_52w_high, 4),

        # Pullback
        "pullback_pct": round(pullback_pct, 4),
        "pullback_vol_shrinking": pullback_vol_shrinking,
        "higher_low": higher_low,

        # Breakout
        "prior_high_20d": round(prior_high_20d, 2),
        "breakout_today": breakout_today,
        "near_breakout": near_breakout,

        # ATR
        "atr": round(atr, 4),
    }
