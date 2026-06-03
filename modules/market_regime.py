"""
modules/market_regime.py
Module 1: Is today's market safe to enter new positions?
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pandas as pd
from config import MARKET_SCORE_MIN, MARKET_SCORE_TRADE


def score_market(market_data: dict) -> dict:
    score = 0
    details = {}
    loaded = [k for k in market_data if market_data[k] is not None]

    if not loaded:
        details["market_score"] = 50  # neutral — don't block screener
        details["action"] = "SELECTIVE"
        details["warning"] = "No market data loaded — defaulting to neutral score 50"
        return details

    # ── QQQ ──────────────────────────────────────────────────
    qqq = market_data.get("QQQ")
    spy = market_data.get("SPY")
    iwm = market_data.get("IWM")
    vix = market_data.get("^VIX")

    if qqq is not None and len(qqq) >= 21:
        qqq_close = qqq["close"]
        qqq_ma20  = qqq_close.rolling(20).mean().iloc[-1]
        qqq_above = qqq_close.iloc[-1] > qqq_ma20
        qqq_5d    = qqq_close.iloc[-1] / qqq_close.iloc[-6] - 1
        details["qqq_above_ma20"] = qqq_above
        details["qqq_5d"] = round(qqq_5d, 4)
        if qqq_above:
            score += 30
        if qqq_5d > 0.01:
            score += 15
        elif qqq_5d > -0.01:
            score += 5

    if spy is not None and len(spy) >= 21:
        spy_close = spy["close"]
        spy_ma20  = spy_close.rolling(20).mean().iloc[-1]
        spy_above = spy_close.iloc[-1] > spy_ma20
        details["spy_above_ma20"] = spy_above
        if spy_above:
            score += 20

    if iwm is not None and len(iwm) >= 21:
        iwm_close = iwm["close"]
        iwm_ma20  = iwm_close.rolling(20).mean().iloc[-1]
        iwm_above = iwm_close.iloc[-1] > iwm_ma20
        details["iwm_above_ma20"] = iwm_above
        if iwm_above:
            score += 20

    if vix is not None and len(vix) >= 6:
        vix_level     = vix["close"].iloc[-1]
        vix_5d_change = vix["close"].iloc[-1] / vix["close"].iloc[-6] - 1
        details["vix_level"]     = round(vix_level, 2)
        details["vix_5d_change"] = round(vix_5d_change, 4)
        if vix_level < 20:
            score += 15
        elif vix_level < 25:
            score += 8
        elif vix_level > 30:
            score -= 15
        if vix_5d_change > 0.20:
            score -= 10

    # If most ETFs failed to load, apply a partial credit
    if len(loaded) < 2:
        score = max(score, 50)   # at least neutral

    score = max(0, min(100, score))
    details["market_score"] = score
    details["loaded_etfs"]  = loaded

    if score >= 80:
        action = "AGGRESSIVE"
    elif score >= MARKET_SCORE_TRADE:
        action = "SELECTIVE"
    elif score >= MARKET_SCORE_MIN:
        action = "WATCHLIST_ONLY"
    else:
        action = "NO_NEW_ENTRIES"

    details["action"] = action
    return details
