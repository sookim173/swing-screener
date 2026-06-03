"""
modules/chart_structure.py
Module 5: Where to enter? Does stop/target make structural sense?
Patterns: Momentum Pullback, Breakout-Retest, Gap Hold
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pandas as pd


def detect_pattern(df: pd.DataFrame, ind: dict) -> dict:
    score = 0
    details = {}
    pattern = None

    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]

    # ── Pattern 1: Momentum Pullback ─────────────────────────
    # Strong run → 1-4 day pullback → volume shrinks → higher low → bounce
    pullback_pct            = ind.get("pullback_pct", 0)
    pullback_vol_shrinking  = ind.get("pullback_vol_shrinking", False)
    higher_low              = ind.get("higher_low", False)
    ret_10d                 = (close.iloc[-1] / close.iloc[-11] - 1) if len(close) >= 11 else 0
    above_ma8               = close.iloc[-1] > ind.get("ma8", 0)
    above_ma20              = ind.get("above_ma20", False)

    pullback_conditions = [
        ret_10d > 0.08,              # strong prior run
        -0.10 < pullback_pct < -0.01, # actual pullback (1~10%)
        pullback_vol_shrinking,      # volume dries up
        higher_low,                  # structural integrity
        above_ma20,                  # trend intact
    ]
    pullback_score = sum(pullback_conditions)

    if pullback_score >= 4:
        pattern = "Momentum Pullback"
        score += 17
        details["pattern_confidence"] = "HIGH"
    elif pullback_score >= 3:
        pattern = "Momentum Pullback (Weak)"
        score += 10
        details["pattern_confidence"] = "MODERATE"

    # ── Pattern 2: Breakout-Retest ───────────────────────────
    # Breakout of 20d high → pullback to breakout level → holds
    prior_high_20d = ind.get("prior_high_20d", 0)
    near_breakout  = ind.get("near_breakout", False)
    breakout_today = ind.get("breakout_today", False)

    # Recent breakout (last 3 days) + current price near breakout level
    recent_break = False
    if len(high) >= 5:
        recent_break = high.iloc[-4:-1].max() > prior_high_20d

    retest_conditions = [
        recent_break,
        near_breakout,                               # price near breakout level
        close.iloc[-1] > prior_high_20d * 0.98,    # holding above
        above_ma20,
    ]
    retest_score = sum(retest_conditions)

    if pattern is None and retest_score >= 3:
        pattern = "Breakout-Retest"
        score += 17
        details["pattern_confidence"] = "HIGH"
    elif pattern is None and retest_score == 2:
        pattern = "Breakout-Retest (Weak)"
        score += 8
        details["pattern_confidence"] = "MODERATE"

    # ── Pattern 3: Gap Hold ───────────────────────────────────
    # Gap up → holds gap day low → VWAP hold → continuation
    ret_1d     = ind.get("ret_1d", 0)
    above_vwap = ind.get("above_vwap", False)

    if len(close) >= 2:
        gap_up = df["open"].iloc[-1] > close.iloc[-2] * 1.03

        gap_conditions = [
            gap_up,
            ret_1d > 0,               # closed above open (held)
            above_vwap,
            above_ma20,
        ]
        gap_score = sum(gap_conditions)

        if pattern is None and gap_score >= 3:
            pattern = "Gap Hold"
            score += 17
            details["pattern_confidence"] = "HIGH"
        elif pattern is None and gap_score == 2:
            pattern = "Gap Hold (Weak)"
            score += 8
            details["pattern_confidence"] = "MODERATE"

    if pattern is None:
        details["pattern_confidence"] = "NONE"

    # ── Structural quality bonuses ────────────────────────────
    if above_ma8:
        score += 3
    if ind.get("ma20_rising", False):
        score += 3

    score = min(score, 30)
    details["pattern"] = pattern if pattern else "No Pattern"
    details["chart_score"] = score

    return details


def find_structural_stop(df: pd.DataFrame, ind: dict, pattern: str) -> float:
    """
    Returns structural stop price based on chart + ATR buffer.
    If stop is >8% away the trade plan R:R check will reject it — no artificial cap.
    """
    low   = df["low"]
    close = df["close"]
    entry = close.iloc[-1]
    atr   = ind.get("atr", entry * 0.03)

    if "Pullback" in (pattern or ""):
        # Below pullback swing low with 0.5 ATR buffer
        stop = low.iloc[-5:].min() - (atr * 0.5)

    elif "Breakout" in (pattern or ""):
        # Below prior consolidation low (last 5 days before breakout)
        stop = low.iloc[-6:-1].min()

    elif "Gap" in (pattern or ""):
        # Below gap day VWAP (use today's low as proxy)
        stop = df["low"].iloc[-1] * 0.99

    else:
        # 1.5 ATR below close
        stop = entry - (atr * 1.5)

    # Minimum: stop must be at least 1% below entry (avoids trivial stops)
    min_stop = entry * 0.99
    stop = min(stop, min_stop)

    return round(stop, 2)
