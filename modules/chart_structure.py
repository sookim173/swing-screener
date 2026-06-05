"""
modules/chart_structure.py
Module 5: Where to enter? Does stop/target make structural sense?

Pattern priority (highest specificity first):
  1. Gap-and-Go Base     — recent big gap, now consolidating tightly
  2. News Consolidation  — prior downtrend + vol explosion + holding highs
  3. Gap Hold            — today's gap still holding
  4. Momentum Pullback   — organic uptrend + light-volume pullback
  5. Breakout-Retest     — breakout of 20d high then retest

Gap-driven patterns always take precedence to avoid mis-labelling
news/catalyst reversals as "Momentum Pullback".
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

    above_ma8  = close.iloc[-1] > ind.get("ma8", 0)
    above_ma20 = ind.get("above_ma20", False)
    atr_v      = ind.get("atr", float(close.iloc[-1]) * 0.03)

    # ── Gap pre-computation (shared by P1, P4, P5) ───────────
    _opens       = df["open"]
    _prev_closes = close.shift(1)
    _gap_series  = (_opens / _prev_closes - 1).iloc[-10:].dropna()
    _max_gap     = float(_gap_series.max()) if not _gap_series.empty else 0
    # A 7%+ single-day open gap in the last 10 sessions is "gap dominant"
    _recent_gap_dominant = _max_gap >= 0.07

    # ═══════════════════════════════════════════════════════
    # Pattern 4 — Gap-and-Go Base  (checked FIRST — most specific)
    # Big gap (5%+) on news 1–10 days ago, now consolidating above gap
    # Prior trend can be DOWN — reversal/catalyst play
    # ═══════════════════════════════════════════════════════
    if len(close) >= 5:
        gap_series   = (_opens / _prev_closes - 1).iloc[-10:]
        max_gap_idx  = gap_series.abs().idxmax()
        max_gap      = float(gap_series[max_gap_idx])

        if max_gap >= 0.05:
            days_since_gap = len(df) - 1 - list(df.index).index(max_gap_idx)

            post_gap          = close.loc[max_gap_idx:]
            post_gap_range    = post_gap.max() - post_gap.min()
            tight_consol      = post_gap_range < atr_v * 2.0 if len(post_gap) > 1 else True

            gap_day_low  = df["low"][max_gap_idx]
            holding_gap  = close.iloc[-1] > gap_day_low

            gap_day_vol      = float(volume[max_gap_idx])
            post_gap_vols    = volume.loc[max_gap_idx:].iloc[1:]
            vol_drying       = post_gap_vols.mean() < gap_day_vol * 0.7 if len(post_gap_vols) > 0 else True

            avg_vol_20       = volume.rolling(20).mean()
            gap_rvol         = gap_day_vol / float(avg_vol_20[max_gap_idx]) if float(avg_vol_20[max_gap_idx]) > 0 else 0

            gab_conds = [
                1 <= days_since_gap <= 10,
                tight_consol,
                holding_gap,
                vol_drying,
                gap_rvol >= 2.0,
            ]
            gab_score = sum(gab_conds)

            if gab_score >= 4:
                pattern = "Gap-and-Go Base"
                score += 17
                details["pattern_confidence"] = "HIGH"
                details["gap_pct"]        = round(max_gap * 100, 1)
                details["days_since_gap"] = int(days_since_gap)
            elif gab_score == 3:
                pattern = "Gap-and-Go Base (Weak)"
                score += 10
                details["pattern_confidence"] = "MODERATE"
                details["gap_pct"]        = round(max_gap * 100, 1)
                details["days_since_gap"] = int(days_since_gap)

    # ═══════════════════════════════════════════════════════
    # Pattern 5 — News Consolidation  (checked second)
    # Prior downtrend → volume explosion → price holds near highs
    # ═══════════════════════════════════════════════════════
    if pattern is None and len(close) >= 10:
        rvol_3d = ind.get("rvol_3d_avg", 0)

        prior_trend_down = close.iloc[-15] > close.iloc[-6] if len(close) >= 15 else False

        recent_5d_high   = high.iloc[-5:].max()
        near_recent_high = close.iloc[-1] >= recent_5d_high * 0.92

        avg_vol_20d  = volume.rolling(20).mean().iloc[-1]
        peak_rvol_5d = float((volume.iloc[-5:] / avg_vol_20d).max()) if avg_vol_20d > 0 else 0

        spike_day_idx    = volume.iloc[-5:].idxmax()
        spike_open       = float(df["open"][spike_day_idx])
        spike_close      = float(close[spike_day_idx])
        spike_size       = spike_close - spike_open
        current_vs_spike = (close.iloc[-1] - spike_open) / spike_size if spike_size > 0 else 1

        nc_conds = [
            prior_trend_down,
            peak_rvol_5d >= 3.0,
            near_recent_high,
            current_vs_spike >= 0.5,
            rvol_3d >= 1.5,
        ]
        nc_score = sum(nc_conds)

        if nc_score >= 4:
            pattern = "News Consolidation"
            score += 15
            details["pattern_confidence"] = "HIGH"
            details["peak_rvol_5d"] = round(peak_rvol_5d, 1)
        elif nc_score == 3:
            pattern = "News Consolidation (Weak)"
            score += 8
            details["pattern_confidence"] = "MODERATE"
            details["peak_rvol_5d"] = round(peak_rvol_5d, 1)

    # ═══════════════════════════════════════════════════════
    # Pattern 3 — Gap Hold  (today's gap still holding)
    # ═══════════════════════════════════════════════════════
    if pattern is None and len(close) >= 2:
        ret_1d     = ind.get("ret_1d", 0)
        above_vwap = ind.get("above_vwap", False)
        gap_up     = df["open"].iloc[-1] > close.iloc[-2] * 1.03

        # gap_up is a hard requirement — without it there is no Gap Hold
        if gap_up:
            gap_conds = [ret_1d > 0, above_vwap, above_ma20]
            gap_score = sum(gap_conds)

            if gap_score >= 2:
                pattern = "Gap Hold"
                score += 17
                details["pattern_confidence"] = "HIGH"
            elif gap_score == 1:
                pattern = "Gap Hold (Weak)"
                score += 8
                details["pattern_confidence"] = "MODERATE"

    # ═══════════════════════════════════════════════════════
    # Pattern 1 — Momentum Pullback
    # Requires organic uptrend (not gap-inflated)
    # ═══════════════════════════════════════════════════════
    if pattern is None:
        pullback_pct           = ind.get("pullback_pct", 0)
        pullback_vol_shrinking = ind.get("pullback_vol_shrinking", False)
        higher_low             = ind.get("higher_low", False)
        ret_10d                = (close.iloc[-1] / close.iloc[-11] - 1) if len(close) >= 11 else 0

        # Disqualify if recent price action is gap-driven
        organic_uptrend = ret_10d > 0.08 and not _recent_gap_dominant

        pullback_conds = [
            organic_uptrend,
            -0.10 < pullback_pct < -0.01,
            pullback_vol_shrinking,
            higher_low,
            above_ma20,
        ]
        pullback_score = sum(pullback_conds)

        if pullback_score >= 4:
            pattern = "Momentum Pullback"
            score += 17
            details["pattern_confidence"] = "HIGH"
        elif pullback_score >= 3:
            pattern = "Momentum Pullback (Weak)"
            score += 10
            details["pattern_confidence"] = "MODERATE"

    # ═══════════════════════════════════════════════════════
    # Pattern 2 — Breakout-Retest
    # ═══════════════════════════════════════════════════════
    if pattern is None:
        prior_high_20d = ind.get("prior_high_20d", 0)
        near_breakout  = ind.get("near_breakout", False)

        recent_break = False
        if len(high) >= 5:
            recent_break = high.iloc[-4:-1].max() > prior_high_20d

        retest_conds = [
            recent_break,
            near_breakout,
            close.iloc[-1] > prior_high_20d * 0.98,
            above_ma20,
        ]
        retest_score = sum(retest_conds)

        if retest_score >= 3:
            pattern = "Breakout-Retest"
            score += 17
            details["pattern_confidence"] = "HIGH"
        elif retest_score == 2:
            pattern = "Breakout-Retest (Weak)"
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
    details["pattern"]     = pattern if pattern else "No Pattern"
    details["chart_score"] = score

    return details


def find_structural_stop(df: pd.DataFrame, ind: dict, pattern: str) -> float:
    """
    Returns structural stop price based on pattern type + ATR buffer.
    Stop logic matched to the thesis of each pattern:
      - Gap-and-Go Base: below gap-day low (gap fill = thesis broken)
      - News Consolidation: below spike-candle low (news reaction undone)
      - Gap Hold: below today's low
      - Momentum Pullback: below pullback swing low
      - Breakout-Retest: below prior consolidation low
    """
    low   = df["low"]
    close = df["close"]
    entry = close.iloc[-1]
    atr   = ind.get("atr", entry * 0.03)

    if "Gap-and-Go" in (pattern or ""):
        opens       = df["open"]
        prev_closes = close.shift(1)
        gap_series  = (opens / prev_closes - 1).iloc[-10:]
        max_gap_idx = gap_series.abs().idxmax()
        stop = df["low"][max_gap_idx] - (atr * 0.3)

    elif "News Consolidation" in (pattern or ""):
        spike_day_idx = df["volume"].iloc[-7:].idxmax()
        stop = df["low"][spike_day_idx] - (atr * 0.3)

    elif "Gap" in (pattern or ""):
        stop = df["low"].iloc[-1] * 0.99

    elif "Pullback" in (pattern or ""):
        stop = low.iloc[-5:].min() - (atr * 0.5)

    elif "Breakout" in (pattern or ""):
        stop = low.iloc[-6:-1].min()

    else:
        stop = entry - (atr * 1.5)

    min_stop = entry * 0.99
    stop = min(stop, min_stop)

    return round(stop, 2)
