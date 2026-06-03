"""
modules/risk_plan.py
Module 6: How much to buy? Where to stop? What's the R:R?
Uses structural stop (not fixed -4%)
"""

import math
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ACCOUNT_SIZE, MAX_STOP_PCT, MIN_RR

RISK_PCT       = 0.02   # risk 2% of account per trade ($20 on $1,000)
MAX_POS_PCT    = 0.25   # max 25% of account per position ($250 on $1,000)
PROFIT_TARGET_R = 2.5   # default target in R multiples


def calculate_trade_plan(
    entry_price: float,
    structural_stop: float,
    atr: float = None,
) -> dict:

    stop_price       = structural_stop
    stop_pct         = (entry_price - stop_price) / entry_price
    risk_per_share   = entry_price - stop_price

    # ATR-based stop suggestion (1.5× ATR below entry) for reference
    atr_stop = round(entry_price - 1.5 * atr, 2) if atr else None
    atr_stop_pct = round((entry_price - atr_stop) / entry_price, 4) if atr_stop else None

    if risk_per_share <= 0:
        return {"trade_ready": False, "reason": "Stop price >= entry price", "rr": 0,
                "atr_stop": atr_stop, "atr_stop_pct": atr_stop_pct}

    # Position sizing: smaller of (2% risk budget) or (25% account cap)
    risk_budget      = ACCOUNT_SIZE * RISK_PCT            # $20
    shares_by_risk   = math.floor(risk_budget / risk_per_share)
    shares_by_size   = math.floor((ACCOUNT_SIZE * MAX_POS_PCT) / entry_price)
    shares           = min(shares_by_risk, shares_by_size)

    if shares == 0:
        return {"trade_ready": False, "reason": "Position size rounds to 0 shares", "rr": 0}

    reward_per_share = risk_per_share * PROFIT_TARGET_R
    target_price     = round(entry_price + reward_per_share, 2)
    position_value   = round(shares * entry_price, 2)
    expected_loss    = round(shares * risk_per_share, 2)
    expected_profit  = round(shares * reward_per_share, 2)
    rr               = round(PROFIT_TARGET_R, 2)

    # ── Trade Ready checks ────────────────────────────────────
    reasons_no = []
    if stop_pct > MAX_STOP_PCT:
        reasons_no.append(f"Stop too wide: {stop_pct:.1%} > {MAX_STOP_PCT:.0%} max — skip this trade")
    if rr < MIN_RR:
        reasons_no.append(f"R:R {rr} below minimum {MIN_RR}")

    trade_ready = len(reasons_no) == 0

    return {
        "entry":          round(entry_price, 2),
        "stop":           round(stop_price, 2),
        "target":         target_price,
        "stop_pct":       round(stop_pct, 4),
        "atr_stop":       atr_stop,
        "atr_stop_pct":   atr_stop_pct,
        "shares":         shares,
        "position_value": position_value,
        "risk_dollars":   expected_loss,
        "profit_dollars": expected_profit,
        "rr":             rr,
        "trade_ready":    trade_ready,
        "reason":         " | ".join(reasons_no) if reasons_no else "All checks passed",
    }
