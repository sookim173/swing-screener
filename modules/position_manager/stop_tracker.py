"""
modules/position_manager/stop_tracker.py
Trailing Stop 업데이트 + 실시간 Stop/Target 자동 계산

Stop 계산 (3가지 중 최적값):
  1. 구조적 손절 (차트 패턴 기반)
  2. ATR 기반  = entry - (ATR × 1.5)
  3. VWAP 기반 = VWAP - 0.5%
  → 셋 중 entry에 가장 가까운 값 (너무 넓은 손절 방지)

Target 계산 (3가지):
  1. R:R 기반   = entry + (risk × 2.5)   ← risk = entry - stop (진입 시 확정)
  2. ATR 기반   = entry + (ATR × 3.75)   ← ATR × 1.5 stop 기준의 2.5R
  3. 저항선 기반 = 최근 20일 고점 또는 52주 고점
  → 보수적 목표: 셋 중 가장 낮은 값

원칙:
  - risk는 entry - stop 으로 진입 시 1회 확정 (current 기준 재계산 금지)
  - Stop은 절대 아래로 내리지 않음
  - 1R → Breakeven
  - 1.5R → EMA8 아래
  - 2R+ → 전일 저점 trailing
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pandas as pd


def calculate_suggested_stops(
    df: pd.DataFrame,
    ind: dict,
    intraday_ind: dict,
    pos: dict,
) -> dict:
    """
    실시간으로 적정 Stop 3가지와 Target 2가지를 계산.
    positions.json의 저장값과 무관하게 현재 차트 기준으로 재계산.
    """
    from modules.chart_structure import detect_pattern, find_structural_stop

    entry   = pos["entry_price"]
    current = intraday_ind.get("current_price") or ind.get("close", entry)
    atr     = ind.get("atr", current * 0.03)
    vwap    = intraday_ind.get("vwap", current)

    # ── 1. 구조적 손절 (차트 패턴 기반) ──────────────────────
    pattern_result = detect_pattern(df, ind)
    pattern        = pattern_result.get("pattern", "No Pattern")
    structural_stop = find_structural_stop(df, ind, pattern)

    # ── 2. ATR 기반 손절 ──────────────────────────────────────
    atr_stop = round(current - (atr * 1.5), 2)

    # ── 3. VWAP 기반 손절 ────────────────────────────────────
    vwap_stop = round(vwap * 0.995, 2)

    # ── 최적 Stop: entry에 가장 가까운 값 (단, entry보다 낮아야) ──
    candidates = [s for s in [structural_stop, atr_stop, vwap_stop] if s < current]
    if candidates:
        suggested_stop = max(candidates)   # entry에 가장 가까운 = 가장 큰 값
    else:
        suggested_stop = atr_stop

    # ── risk: entry 기준으로 확정 (current 재계산 금지) ────────
    # pos에 저장된 risk_per_share 우선 사용, 없으면 entry - suggested_stop 으로 산정
    saved_risk = pos.get("risk_per_share", 0)
    if saved_risk > 0.01:
        risk = saved_risk
    else:
        risk = entry - suggested_stop

    # ── Target 1: R:R 2.5 기반 (entry 기준) ─────────────────
    rr_target = round(entry + (risk * 2.5), 2) if risk > 0 else round(entry * 1.15, 2)

    # ── Target 2: ATR 기반 (entry - ATR×1.5 stop 전제의 2.5R) ─
    atr_target = round(entry + (atr * 1.5 * 2.5), 2)   # = entry + ATR × 3.75

    # ── Target 3: 저항선 기반 ────────────────────────────────
    high = df["high"]
    resistance_20d = round(float(high.iloc[-22:].max()), 2)
    resistance_52w = round(float(high.rolling(252).max().iloc[-1])
                           if len(high) >= 252 else high.max(), 2)

    resistances = [r for r in [resistance_20d, resistance_52w] if r > current]
    resistance_target = min(resistances) if resistances else rr_target

    # ── 보수적 목표: 셋 중 가장 낮은 값 ─────────────────────
    conservative_target = min(rr_target, atr_target, resistance_target)

    return {
        # Stop 3가지
        "structural_stop":   structural_stop,
        "atr_stop":          atr_stop,
        "vwap_stop":         vwap_stop,
        "suggested_stop":    suggested_stop,

        # Target 3가지
        "rr_target":          rr_target,
        "atr_target":         atr_target,
        "resistance_target":  resistance_target,
        "conservative_target": conservative_target,

        # 참고 정보
        "pattern":           pattern,
        "atr":               round(atr, 2),
        "risk_per_share":    round(risk, 2),
        "suggested_rr":      round((conservative_target - current) / risk, 2) if risk > 0 else 0,
    }


def update_trailing_stop(
    pos: dict,
    intraday_ind: dict,
    daily_ind: dict,
) -> dict:
    """
    현재 수익 R에 따라 stop 가격 업데이트.
    반환: {"new_stop": float, "stop_moved": bool, "stop_reason": str}
    """
    entry    = pos["entry_price"]
    risk     = pos.get("risk_per_share", entry * 0.05)
    current  = intraday_ind.get("current_price") or daily_ind.get("close", entry)
    old_stop = pos.get("current_stop", pos.get("structural_stop", entry * 0.95))

    if risk <= 0:
        return {"new_stop": old_stop, "stop_moved": False,
                "stop_reason": "risk=0", "unrealized_R": 0}

    unrealized_R = (current - entry) / risk

    ema8     = intraday_ind.get("ema8",  daily_ind.get("ma8",  entry))
    prev_low = daily_ind.get("low", entry * 0.97)

    if unrealized_R >= 2.0:
        candidate   = max(prev_low * 0.995, ema8 * 0.99)
        stop_reason = "2R+ trailing (prev_low / EMA8)"
    elif unrealized_R >= 1.5:
        candidate   = ema8 * 0.99
        stop_reason = "1.5R trailing (EMA8)"
    elif unrealized_R >= 1.0:
        candidate   = entry
        stop_reason = "1R → Breakeven"
    elif unrealized_R >= 0.5:
        candidate   = old_stop
        stop_reason = "0.5R 미만 — 구조적 손절 유지"
    else:
        candidate   = old_stop
        stop_reason = "손실 구간 — stop 고정"

    # 절대 원칙: stop은 아래로 내리지 않는다
    new_stop   = max(candidate, old_stop)
    stop_moved = new_stop > old_stop

    return {
        "new_stop":     round(new_stop, 2),
        "stop_moved":   stop_moved,
        "stop_reason":  stop_reason,
        "unrealized_R": round(unrealized_R, 2),
    }
