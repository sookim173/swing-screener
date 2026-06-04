"""
modules/position_manager/intraday_data.py
5분봉 데이터 수집 및 지표 계산

소스:
  - yfinance  : 5분봉 OHLCV (당일, 무료, 15분 지연)
  - Finnhub   : 실시간 현재가 (WebSocket or REST)
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def get_intraday_df(ticker: str, interval: str = "5m") -> pd.DataFrame | None:
    """
    yfinance로 당일 5분봉 데이터 수집.
    장 중: 당일 데이터
    장 후/장 전: 가장 최근 거래일 데이터
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        df = t.history(period="1d", interval=interval)

        if df is None or df.empty:
            return None

        df.columns = [c.lower() for c in df.columns]
        df = df[["open", "high", "low", "close", "volume"]].copy()
        df.dropna(inplace=True)
        return df

    except Exception:
        return None


def calculate_intraday_indicators(df: pd.DataFrame) -> dict:
    """
    5분봉 데이터에서 판별에 필요한 지표 계산.
    """
    if df is None or len(df) < 3:
        return {}

    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]
    open_  = df["open"]

    # ── VWAP ─────────────────────────────────────────────────
    typical_price = (high + low + close) / 3
    cum_tp_vol    = (typical_price * volume).cumsum()
    cum_vol       = volume.cumsum()
    vwap          = cum_tp_vol / cum_vol
    current_vwap  = float(vwap.iloc[-1])
    above_vwap    = float(close.iloc[-1]) > current_vwap

    # ── EMA 8, 21 (분봉 기준) ─────────────────────────────────
    ema8  = close.ewm(span=8,  adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    above_ema8  = float(close.iloc[-1]) > float(ema8.iloc[-1])
    above_ema21 = float(close.iloc[-1]) > float(ema21.iloc[-1])

    # ── 현재 캔들 분석 ─────────────────────────────────────────
    last_open  = float(open_.iloc[-1])
    last_close = float(close.iloc[-1])
    last_high  = float(high.iloc[-1])
    last_low   = float(low.iloc[-1])
    candle_range = last_high - last_low

    # 윗꼬리 비율 (매도 압력 신호)
    upper_wick = last_high - max(last_open, last_close)
    upper_wick_ratio = upper_wick / candle_range if candle_range > 0 else 0

    # ── 최근 5개 봉 Higher High / Higher Low ───────────────────
    recent_highs  = high.iloc[-6:].values
    recent_lows   = low.iloc[-6:].values
    higher_high   = bool(recent_highs[-1] > recent_highs[-2]) if len(recent_highs) >= 2 else False
    higher_low    = bool(recent_lows[-1]  > recent_lows[-2])  if len(recent_lows)  >= 2 else False
    prev_hl_price = round(float(recent_lows[-2]), 2) if len(recent_lows) >= 2 else None
    curr_low_price = round(float(recent_lows[-1]), 2) if len(recent_lows) >= 1 else None

    # ── 거래량 분석 ───────────────────────────────────────────
    avg_vol_intraday = float(volume.mean())
    last_vol         = float(volume.iloc[-1])
    vol_ratio        = last_vol / avg_vol_intraday if avg_vol_intraday > 0 else 1.0

    # 최근 3봉 상승봉 vs 하락봉 거래량 비교
    up_candles   = df[close > open_].tail(6)
    down_candles = df[close < open_].tail(6)
    avg_up_vol   = float(up_candles["volume"].mean())   if len(up_candles)   > 0 else 0
    avg_down_vol = float(down_candles["volume"].mean()) if len(down_candles) > 0 else 0
    buying_pressure = avg_up_vol > avg_down_vol

    # ── 전일 저점 대비 ────────────────────────────────────────
    prev_day_low = float(low.iloc[0])  # 당일 첫 봉 저점 (프록시)

    # ── 장 첫 15분 (3봉) 반응 ────────────────────────────────
    first_15min_high = float(high.iloc[:3].max()) if len(df) >= 3 else float(high.iloc[0])
    first_15min_low  = float(low.iloc[:3].min())  if len(df) >= 3 else float(low.iloc[0])
    current_above_open_range = float(close.iloc[-1]) > first_15min_high

    return {
        "current_price":      round(float(close.iloc[-1]), 2),
        "vwap":               round(current_vwap, 2),
        "above_vwap":         above_vwap,
        "ema8":               round(float(ema8.iloc[-1]), 2),
        "ema21":              round(float(ema21.iloc[-1]), 2),
        "above_ema8":         above_ema8,
        "above_ema21":        above_ema21,
        "upper_wick_ratio":   round(upper_wick_ratio, 3),
        "higher_high_5m":     higher_high,
        "higher_low_5m":      higher_low,
        "prev_low_price":     prev_hl_price,    # 직전 저점 가격
        "curr_low_price":     curr_low_price,   # 현재 저점 가격
        "vol_ratio_intraday": round(vol_ratio, 2),
        "buying_pressure":    buying_pressure,
        "prev_day_low_proxy": round(prev_day_low, 2),
        "first_15min_high":   round(first_15min_high, 2),
        "first_15min_low":    round(first_15min_low, 2),
        "above_open_range":   current_above_open_range,
    }
