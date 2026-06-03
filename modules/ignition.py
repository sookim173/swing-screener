"""
modules/ignition.py
Module 2: Is money entering this stock RIGHT NOW?
Primary signal: RVOL spike
Day 2 will add: Premarket gap/volume
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import RVOL_MIN, RVOL_STRONG


def score_ignition(ind: dict, pm_gap_pct: float = None, pm_volume_ratio: float = None) -> dict:
    score = 0
    details = {}

    rvol = ind.get("rvol", 0)
    ret_1d = ind.get("ret_1d", 0)
    above_vwap = ind.get("above_vwap", False)

    details["rvol"] = rvol
    details["ret_1d"] = ret_1d
    details["above_vwap"] = above_vwap

    # ── RVOL scoring ─────────────────────────────────────────
    if rvol >= 5.0:
        score += 20
    elif rvol >= RVOL_STRONG:       # 3x
        score += 16
    elif rvol >= RVOL_MIN:          # 2x
        score += 10
    elif rvol >= 1.5:
        score += 5
    else:
        score += 0

    details["rvol_score"] = score

    # ── Price + Volume alignment ──────────────────────────────
    # Price going up with volume = real buying
    if ret_1d > 0 and rvol >= RVOL_MIN:
        score += 8
    elif ret_1d > 0.03 and rvol >= 1.5:
        score += 4

    # ── VWAP ─────────────────────────────────────────────────
    if above_vwap:
        score += 6

    # ── Premarket (Day 2) — placeholder scoring ───────────────
    pm_score = 0
    if pm_gap_pct is not None:
        details["pm_gap_pct"] = pm_gap_pct
        if 0.03 <= pm_gap_pct <= 0.08:        # +3~8% ideal
            pm_score += 10
        elif 0.08 < pm_gap_pct <= 0.15:       # +8~15% strong
            pm_score += 8
        elif 0.15 < pm_gap_pct <= 0.30:       # +15~30% check catalyst
            pm_score += 4
        elif pm_gap_pct > 0.30:               # too much gap - context needed
            pm_score += 2
        score += pm_score

    if pm_volume_ratio is not None:            # PM vol vs avg PM vol
        details["pm_volume_ratio"] = pm_volume_ratio
        if pm_volume_ratio >= 3.0:
            score += 6
        elif pm_volume_ratio >= 1.5:
            score += 3

    score = min(score, 40)   # cap at 40 for this module
    details["ignition_score"] = score
    details["ignition_grade"] = "STRONG" if score >= 28 else "MODERATE" if score >= 16 else "WEAK"

    return details
