"""
modules/basic_filter.py
Module: Basic liquidity/price filter + momentum universe filter
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import *


def pass_basic_filter(info: dict, ind: dict) -> tuple[bool, str]:
    """
    Returns (passed: bool, reason: str)
    """
    close = ind.get("close", 0)
    market_cap = info.get("market_cap", 0)
    avg_dollar_vol = ind.get("avg_dollar_vol", 0)
    avg_vol = info.get("avg_volume", 0)
    exchange = info.get("exchange", "")

    if not (PRICE_MIN <= close <= PRICE_MAX):
        return False, f"Price ${close} out of range (${PRICE_MIN}~${PRICE_MAX})"

    if market_cap and not (MARKET_CAP_MIN <= market_cap <= MARKET_CAP_MAX):
        mc_b = round(market_cap / 1e9, 2)
        return False, f"Market cap ${mc_b}B out of range"

    if avg_dollar_vol < AVG_DOLLAR_VOLUME_MIN:
        m = round(avg_dollar_vol / 1e6, 1)
        return False, f"Dollar volume ${m}M below ${AVG_DOLLAR_VOLUME_MIN/1e6}M min"

    if avg_vol and avg_vol < AVG_VOLUME_MIN:
        return False, f"Avg volume {avg_vol:,} below {AVG_VOLUME_MIN:,}"

    return True, "OK"


def pass_momentum_filter(ind: dict, qqq_ret_20d: float = 0) -> tuple[bool, str]:
    """
    Universe filter: remove dead stocks
    Not an entry signal — just removes stocks with no momentum
    """
    ret_5d = ind.get("ret_5d", 0)
    ret_20d = ind.get("ret_20d", 0)
    rvol = ind.get("rvol", 0)
    above_ma20 = ind.get("above_ma20", False)

    if ret_5d < RETURN_5D_MIN:
        return False, f"5d return {ret_5d:.1%} below {RETURN_5D_MIN:.0%}"

    if ret_20d < RETURN_20D_MIN:
        return False, f"20d return {ret_20d:.1%} below {RETURN_20D_MIN:.0%}"

    if not above_ma20:
        return False, "Price below 20MA"

    if rvol < 1.0:
        return False, f"RVOL {rvol:.1f} too low"

    # Relative strength vs QQQ
    rs_vs_qqq = ret_20d - qqq_ret_20d
    if rs_vs_qqq < 0:
        return False, f"Underperforming QQQ by {abs(rs_vs_qqq):.1%}"

    return True, "OK"
