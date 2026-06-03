"""
modules/position_manager/stop_tracker.py
Trailing Stop 업데이트 로직

원칙:
  - Stop은 절대 아래로 내리지 않음
  - R 기준으로 단계적으로 올림
  - 1R 도달 → Breakeven
  - 1.5R 도달 → 전일 저점 또는 EMA8 아래
  - 2R 도달 → 대부분 청산 (runner 일부만 trailing)
"""


def update_trailing_stop(
    pos: dict,
    intraday_ind: dict,
    daily_ind: dict,
) -> dict:
    """
    현재 수익 R에 따라 stop 가격 업데이트.
    반환: {"new_stop": float, "stop_moved": bool, "stop_reason": str}
    """
    entry      = pos["entry_price"]
    risk       = pos["risk_per_share"]
    current    = intraday_ind.get("current_price") or daily_ind.get("close", entry)
    old_stop   = pos.get("current_stop", pos["structural_stop"])

    if risk <= 0:
        return {"new_stop": old_stop, "stop_moved": False, "stop_reason": "risk=0"}

    unrealized_R = (current - entry) / risk

    # ── R 기준 Trailing Stop 단계 ────────────────────────────
    ema8     = intraday_ind.get("ema8",  daily_ind.get("ma8",  entry))
    prev_low = daily_ind.get("low",  entry * 0.97)   # 일봉 당일 저점

    if unrealized_R >= 2.0:
        # 2R 이상: 전일 저점 - 0.5% 또는 EMA8 중 높은 것
        candidate = max(prev_low * 0.995, ema8 * 0.99)
        stop_reason = f"2R+ trailing (prev_low/EMA8)"

    elif unrealized_R >= 1.5:
        # 1.5R: EMA8 아래
        candidate   = ema8 * 0.99
        stop_reason = "1.5R trailing (EMA8)"

    elif unrealized_R >= 1.0:
        # 1R: Breakeven (entry)
        candidate   = entry
        stop_reason = "1R → Breakeven"

    elif unrealized_R >= 0.5:
        # 0.5R: 구조적 손절 유지 (아직 올리지 않음)
        candidate   = old_stop
        stop_reason = "0.5R 미만 — 구조적 손절 유지"

    else:
        # 손실 중: 손절 내리지 않음
        candidate   = old_stop
        stop_reason = "손실 구간 — stop 고정"

    # 절대 원칙: stop은 아래로 내리지 않는다
    new_stop   = max(candidate, old_stop)
    stop_moved = new_stop > old_stop

    return {
        "new_stop":    round(new_stop, 2),
        "stop_moved":  stop_moved,
        "stop_reason": stop_reason,
        "unrealized_R": round(unrealized_R, 2),
    }
