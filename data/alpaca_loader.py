"""
data/alpaca_loader.py
Alpaca Markets 실시간 데이터 로더

기능:
  - get_alpaca_bars()  : 특정 종목 1분봉/5분봉 DataFrame 반환
  - get_live_price()   : 최신 단일 가격 (last trade)
  - get_multi_bars()   : 여러 종목 동시 fetch
"""

import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Literal

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_API_KEY    = os.getenv("ALPACA_API_KEY", "")
_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")

ALPACA_READY = bool(_API_KEY and _SECRET_KEY)

# ── 클라이언트 싱글톤 ──────────────────────────────────────
_data_client   = None
_trading_client = None


def _get_data_client():
    global _data_client
    if _data_client is None:
        from alpaca.data.historical import StockHistoricalDataClient
        _data_client = StockHistoricalDataClient(
            api_key=_API_KEY, secret_key=_SECRET_KEY
        )
    return _data_client


def _get_trading_client():
    global _trading_client
    if _trading_client is None:
        from alpaca.trading.client import TradingClient
        _trading_client = TradingClient(
            api_key=_API_KEY, secret_key=_SECRET_KEY, paper=True
        )
    return _trading_client


# ── 핵심 함수 ──────────────────────────────────────────────

def get_alpaca_bars(
    ticker: str,
    timeframe: Literal["1m", "5m", "15m", "1d"] = "1m",
    hours_back: float = 7.0,
    feed: str = "iex",
) -> pd.DataFrame | None:
    """
    Alpaca에서 분봉 데이터를 가져와 표준 OHLCV DataFrame으로 반환.

    Parameters
    ----------
    ticker     : 종목 심볼
    timeframe  : '1m' | '5m' | '15m' | '1d'
    hours_back : 몇 시간치를 가져올지 (기본 7h = 하루치 커버)
    feed       : 'iex' (무료) | 'sip' (유료)

    Returns
    -------
    DataFrame (index=timestamp, columns=open/high/low/close/volume)
    None on error
    """
    if not ALPACA_READY:
        return None

    try:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        tf_map = {
            "1m":  TimeFrame(1,  TimeFrameUnit.Minute),
            "5m":  TimeFrame(5,  TimeFrameUnit.Minute),
            "15m": TimeFrame(15, TimeFrameUnit.Minute),
            "1d":  TimeFrame(1,  TimeFrameUnit.Day),
        }
        tf = tf_map.get(timeframe, TimeFrame(1, TimeFrameUnit.Minute))

        end   = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours_back)

        req = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=tf,
            start=start,
            end=end,
            feed=feed,
        )
        bars = _get_data_client().get_stock_bars(req)
        df = bars.df

        if df is None or df.empty:
            return None

        # multi-index 해제 (symbol, timestamp) → timestamp only
        if df.index.nlevels > 1:
            df = df.xs(ticker, level=0)

        # 컬럼 소문자 정규화
        df.columns = [c.lower() for c in df.columns]
        needed = ["open", "high", "low", "close", "volume"]
        df = df[[c for c in needed if c in df.columns]].copy()
        df = df[~df.index.duplicated(keep="last")].sort_index()

        return df

    except Exception as e:
        print(f"    [alpaca_loader] {ticker}: {e}")
        return None


def get_multi_bars(
    tickers: list[str],
    timeframe: str = "1m",
    hours_back: float = 7.0,
    feed: str = "iex",
) -> dict[str, pd.DataFrame]:
    """여러 종목을 한 번의 API 호출로 fetch (효율적)."""
    if not ALPACA_READY or not tickers:
        return {}

    try:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        tf_map = {
            "1m":  TimeFrame(1,  TimeFrameUnit.Minute),
            "5m":  TimeFrame(5,  TimeFrameUnit.Minute),
            "15m": TimeFrame(15, TimeFrameUnit.Minute),
            "1d":  TimeFrame(1,  TimeFrameUnit.Day),
        }
        tf  = tf_map.get(timeframe, TimeFrame(1, TimeFrameUnit.Minute))
        end = datetime.now(timezone.utc)
        req = StockBarsRequest(
            symbol_or_symbols=tickers,
            timeframe=tf,
            start=end - timedelta(hours=hours_back),
            end=end,
            feed=feed,
        )
        bars = _get_data_client().get_stock_bars(req)
        df_all = bars.df

        result = {}
        for ticker in tickers:
            try:
                df = df_all.xs(ticker, level=0).copy() if df_all.index.nlevels > 1 \
                     else df_all.copy()
                df.columns = [c.lower() for c in df.columns]
                needed = ["open", "high", "low", "close", "volume"]
                df = df[[c for c in needed if c in df.columns]]
                df = df[~df.index.duplicated(keep="last")].sort_index()
                if not df.empty:
                    result[ticker] = df
            except KeyError:
                pass   # 해당 종목 데이터 없음

        return result

    except Exception as e:
        print(f"    [alpaca_loader] multi_bars error: {e}")
        return {}


def get_live_price(ticker: str) -> float | None:
    """최신 거래 가격 반환 (last trade price)."""
    if not ALPACA_READY:
        return None
    try:
        from alpaca.data.requests import StockLatestTradeRequest
        req  = StockLatestTradeRequest(symbol_or_symbols=ticker)
        resp = _get_data_client().get_stock_latest_trade(req)
        return float(resp[ticker].price)
    except Exception as e:
        print(f"    [alpaca_loader] live_price {ticker}: {e}")
        return None


def get_account_info() -> dict:
    """Paper account 정보 반환."""
    try:
        acct = _get_trading_client().get_account()
        return {
            "status":        str(acct.status),
            "portfolio":     float(acct.portfolio_value),
            "buying_power":  float(acct.buying_power),
            "cash":          float(acct.cash),
        }
    except Exception as e:
        print(f"    [alpaca_loader] account: {e}")
        return {}
