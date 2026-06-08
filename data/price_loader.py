"""
data/price_loader.py
Price & volume data:
  - yfinance : OHLCV history + fundamentals (float, short interest, market cap)
  - Finnhub  : pre-market gap/volume via REST  (set FINNHUB_API_KEY in .env)

Finnhub setup (free):
  1. https://finnhub.io → "Get free API key"
  2. .env 파일에 FINNHUB_API_KEY=your_key 추가
"""

import os
import time
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# .env 로드 (있으면) — swing_screener 루트 기준
try:
    from dotenv import load_dotenv
    import pathlib
    _env_path = pathlib.Path(__file__).parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path)
except Exception:
    pass

_info_cache: dict = {}
_cache_ts:   dict = {}
CACHE_TTL = 3600  # 1 hour

# ── Finnhub setup ─────────────────────────────────────────
FINNHUB_READY  = False
_finnhub_client = None

try:
    import finnhub
    _FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")
    if _FINNHUB_KEY:
        _finnhub_client = finnhub.Client(api_key=_FINNHUB_KEY)
        FINNHUB_READY   = True
except ImportError:
    pass


def get_price_data(ticker: str, days: int = 60) -> pd.DataFrame | None:
    """OHLCV data using Ticker.history() — works with yfinance 0.2+"""
    try:
        t = yf.Ticker(ticker)
        # Use period string instead of start/end for reliability
        period = "3mo" if days <= 65 else "6mo"
        df = t.history(period=period, auto_adjust=True)

        if df is None or df.empty or len(df) < 20:
            return None

        # Normalize column names
        df.columns = [c.lower() for c in df.columns]

        # Keep only OHLCV
        needed = ["open", "high", "low", "close", "volume"]
        df = df[[c for c in needed if c in df.columns]].dropna()

        return df

    except Exception as e:
        print(f"    [price_loader] {ticker}: {e}")
        return None


def get_ticker_info(ticker: str) -> dict:
    """Market cap, float, short interest via yfinance. Results cached 1 hour."""
    now = time.time()
    if ticker in _info_cache and (now - _cache_ts.get(ticker, 0)) < CACHE_TTL:
        return _info_cache[ticker]

    try:
        t    = yf.Ticker(ticker)
        fi   = t.fast_info
        info = {}
        try:
            info = t.info
        except Exception:
            pass

        market_cap   = getattr(fi, "market_cap", None) or info.get("marketCap", 0)
        # floatShares is the correct field for free float (NOT fi.shares which is shares outstanding)
        float_shares = info.get("floatShares", 0) or 0
        short_pct    = info.get("shortPercentOfFloat", 0) or 0
        shares_short = info.get("sharesShort", 0) or 0
        avg_vol      = getattr(fi, "three_month_average_volume", None) or info.get("averageVolume", 0)
        bid          = getattr(fi, "last_price", None) or info.get("bid", 0)
        exchange     = info.get("exchange", "") or getattr(fi, "exchange", "")
        sector       = info.get("sector", "Unknown")

        result = {
            "market_cap":      market_cap or 0,
            "float_shares":    float_shares,
            "shares_short":    shares_short,
            "short_pct_float": short_pct,
            "avg_volume":      avg_vol or 0,
            "avg_volume_10d":  avg_vol or 0,
            "bid":             bid or 0,
            "ask":             bid or 0,
            "sector":          sector,
            "industry":        info.get("industry", "Unknown"),
            "exchange":        exchange,
        }
        _info_cache[ticker] = result
        _cache_ts[ticker]   = now
        return result

    except Exception as e:
        print(f"    [ticker_info] {ticker}: {e}")
        return {}


def get_market_data(etf_list: list) -> dict:
    """Fetch recent data for market ETFs.

    During regular market hours the last daily candle's close is replaced with
    the live price so that MA comparisons reflect intraday conditions.
    """
    result = {}
    in_market = _is_regular_market_open()
    for ticker in etf_list:
        df = get_price_data(ticker, days=60)
        if df is not None:
            if in_market:
                try:
                    live_price = yf.Ticker(ticker).fast_info.last_price
                    if live_price and live_price > 0:
                        df = df.copy()
                        df.iloc[-1, df.columns.get_loc("close")] = live_price
                except Exception:
                    pass
            result[ticker] = df
        else:
            print(f"    [market_data] Could not load {ticker}")
    return result


def get_universe(tickers: list) -> list:
    data = []
    for ticker in tickers:
        df = get_price_data(ticker)
        if df is None:
            continue
        info = get_ticker_info(ticker)
        data.append({"ticker": ticker, "df": df, "info": info})
    return data


# ── Finnhub: Pre-market & real-time data ─────────────────

def _et_offset() -> int:
    """Return UTC offset for US Eastern Time in hours (-4 EDT / -5 EST)."""
    import time as _time
    # DST: second Sunday March ~ first Sunday November
    month = datetime.now().month
    return -4 if 3 <= month <= 11 else -5


def _is_regular_market_open() -> bool:
    """Return True if US regular session is currently active (9:30–16:00 ET, Mon–Fri)."""
    now_et = datetime.now(timezone.utc) + timedelta(hours=_et_offset())
    if now_et.weekday() >= 5:
        return False
    open_t  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_t = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_t <= now_et <= close_t


def get_premarket_data(ticker: str) -> dict:
    """
    Pre-market gap % + volume ratio.

    Data sources:
      - pm_gap_pct      : Finnhub /quote (무료, 실시간)
                          Finnhub 미설정 시 yfinance 1분봉으로 fallback
      - pm_volume_ratio : yfinance 1분봉 prepost=True (무료)
                          pm_volume / (avg_daily_vol * 0.10)

    Note: Finnhub /stock/candle은 유료 플랜 전용 → yfinance로 대체.
    """
    result = {
        "pm_gap_pct":      None,
        "pm_volume_ratio": None,
        "pm_high":         None,
        "pm_low":          None,
        "finnhub_ready":   FINNHUB_READY,
    }

    try:
        # ── Step 1: Gap % ─────────────────────────────────
        if FINNHUB_READY:
            # Finnhub /quote: 실시간 현재가 + 전일 종가
            quote         = _finnhub_client.quote(ticker)
            prev_close    = quote.get("pc", 0)
            current_price = quote.get("c", 0)
            if prev_close and current_price:
                result["pm_gap_pct"] = round((current_price / prev_close) - 1, 4)
        else:
            # Fallback: yfinance fast_info 현재가
            t = yf.Ticker(ticker)
            fi = t.fast_info
            current_price = getattr(fi, "last_price", None) or 0
            prev_close    = getattr(fi, "previous_close", None) or 0
            if prev_close and current_price:
                result["pm_gap_pct"] = round((current_price / prev_close) - 1, 4)

        # ── Step 2: Pre-market volume via yfinance 1분봉 ──
        # prepost=True → 4:00~9:30 AM ET pre-market 포함
        t_obj  = yf.Ticker(ticker)
        df_1m  = t_obj.history(period="1d", interval="1m", prepost=True)

        if df_1m is not None and not df_1m.empty:
            df_1m.columns = [c.lower() for c in df_1m.columns]

            # Pre-market 구간만 필터 (timezone-aware index)
            idx = df_1m.index
            if hasattr(idx, "tz") and idx.tz is not None:
                et_off = _et_offset()
                # 9:30 AM ET 이전 = pre-market
                cutoff_utc = datetime.now(timezone.utc).replace(
                    hour=9 - et_off, minute=30, second=0, microsecond=0
                )
                pm_df = df_1m[df_1m.index < cutoff_utc]
            else:
                pm_df = df_1m  # timezone 없으면 전체 사용

            if not pm_df.empty and "volume" in pm_df.columns:
                pm_volume = int(pm_df["volume"].sum())
                pm_high   = float(pm_df["high"].max())
                pm_low    = float(pm_df["low"].min())
                result["pm_high"] = round(pm_high, 2)
                result["pm_low"]  = round(pm_low, 2)

                # PM volume ratio vs proxy (avg daily * 10%)
                hist = get_price_data(ticker)
                if hist is not None and len(hist) >= 20:
                    avg_daily_vol    = float(hist["volume"].rolling(20).mean().iloc[-1])
                    avg_pm_vol_proxy = avg_daily_vol * 0.10
                    if pm_volume > 0 and avg_pm_vol_proxy > 0:
                        result["pm_volume_ratio"] = round(pm_volume / avg_pm_vol_proxy, 2)

    except Exception:
        pass   # non-fatal — screener continues without PM data

    return result


def get_realtime_quote(ticker: str) -> dict | None:
    """
    Fetch real-time last price and intraday volume via Finnhub /quote.
    Used by the position monitor for intraday RVOL approximation.

    intraday_rvol = current_volume / (avg_daily_vol * elapsed_day_fraction)
    """
    if not FINNHUB_READY:
        return None

    try:
        quote = _finnhub_client.quote(ticker)
        current_price  = quote.get("c", 0)
        current_volume = quote.get("v", 0)   # cumulative volume since open (not pre-market)

        if not current_price:
            return None

        # Elapsed fraction of trading day (9:30 ~ 16:00 ET = 390 min)
        et_off      = _et_offset()
        now_utc     = datetime.now(timezone.utc)
        open_utc    = now_utc.replace(hour=9 - et_off, minute=30, second=0, microsecond=0)
        elapsed_min = max((now_utc - open_utc).total_seconds() / 60, 1)
        day_fraction = min(elapsed_min / 390, 1.0)

        return {
            "price":         round(current_price, 2),
            "volume":        int(current_volume),
            "day_fraction":  round(day_fraction, 4),
            "prev_close":    quote.get("pc", 0),
            "open":          quote.get("o", 0),
            "high":          quote.get("h", 0),
            "low":           quote.get("l", 0),
        }

    except Exception:
        return None
