"""
modules/supply_structure.py
Module 4: Can small buying pressure move this stock significantly?
Float, Short Interest, Liquidity
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import FLOAT_MIN, FLOAT_MAX, SHORT_INTEREST_STRONG


def score_supply(info: dict) -> dict:
    score = 0
    details = {}

    float_shares   = info.get("float_shares", 0)
    short_pct      = info.get("short_pct_float", 0)
    avg_dollar_vol = info.get("avg_volume", 0) * info.get("bid", 1)  # rough proxy

    details["float_shares"] = float_shares
    details["short_pct_float"] = short_pct

    # ── Float scoring ─────────────────────────────────────────
    if float_shares > 0:
        if 10_000_000 <= float_shares <= 30_000_000:
            score += 14    # sweet spot for momentum
            float_grade = "IDEAL"
        elif 30_000_000 < float_shares <= 80_000_000:
            score += 12    # good
            float_grade = "GOOD"
        elif 80_000_000 < float_shares <= 150_000_000:
            score += 6
            float_grade = "OK"
        elif float_shares < 10_000_000:
            score += 4     # too small = risky
            float_grade = "RISKY_SMALL"
        else:
            score += 2
            float_grade = "HEAVY"
    else:
        float_grade = "UNKNOWN"

    details["float_grade"] = float_grade

    # ── Short Interest scoring ────────────────────────────────
    if short_pct >= SHORT_INTEREST_STRONG:    # 15%+
        score += 10
        squeeze_potential = "HIGH"
    elif short_pct >= 0.10:                   # 10~15%
        score += 6
        squeeze_potential = "MODERATE"
    elif short_pct >= 0.05:                   # 5~10%
        score += 3
        squeeze_potential = "LOW"
    else:
        squeeze_potential = "NONE"

    details["squeeze_potential"] = squeeze_potential

    # ── Data freshness warning ────────────────────────────────
    # Short interest is reported bi-monthly by FINRA
    # Flag for user awareness
    details["short_data_warning"] = "Short interest data may be 2-4 weeks old (FINRA bi-monthly)"

    score = min(score, 28)
    details["supply_score"] = score
    details["supply_grade"] = "STRONG" if score >= 20 else "MODERATE" if score >= 12 else "WEAK"

    return details
