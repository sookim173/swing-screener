"""
modules/entry_validator.py
Phase 2: Intraday Entry Validation Engine

State Machine:
  WATCH → SETTING_UP → BUYABLE
                     → WEAKENING → FAILED
                  → FAILED (directly)

Entry Score (0-100):
  VWAP      25pts
  ORB       25pts
  Volume    20pts
  Structure 20pts
  Position  10pts
"""

import pandas as pd
import numpy as np


# ── 메인 엔진 ─────────────────────────────────────────────

def validate_entry(
    df_5m: pd.DataFrame,
    avg_daily_vol: float,
    opp_score: float = 0,
) -> dict:
    """
    5분봉 DataFrame + 평균일거래량 → Entry Score + Status + Signals.

    Returns:
        entry_score   : 0-100
        engine_status : WATCH / SETTING_UP / BUYABLE / WEAKENING / FAILED
        reason        : 한 줄 요약
        failed_reasons: list[str]
        signals       : 상세 신호 dict
        score_breakdown: 점수 구성 dict
    """
    empty = _empty_result()
    if df_5m is None or len(df_5m) < 3:
        empty["reason"] = "Intraday 데이터 부족"
        return empty

    df = df_5m.copy()
    df.columns = [c.lower() for c in df.columns]

    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    open_  = df["open"]
    volume = df["volume"]

    price = float(close.iloc[-1])

    # ── 1. VWAP ──────────────────────────────────────────
    tp          = (high + low + close) / 3
    vwap_series = (tp * volume).cumsum() / volume.cumsum()
    vwap        = float(vwap_series.iloc[-1])

    above_vwap       = price > vwap
    vwap_dist_pct    = round((price - vwap) / vwap * 100, 2) if vwap else 0
    bars_above_vwap  = int((close > vwap_series).sum())
    bars_below_vwap  = int((close <= vwap_series).sum())
    total_bars       = len(df)

    # VWAP reclaim: 직전 3봉 중 VWAP 아래였다가 지금 위
    vwap_reclaim = False
    if len(df) >= 4:
        prev_3_below = (close.iloc[-4:-1] <= vwap_series.iloc[-4:-1]).any()
        vwap_reclaim = bool(prev_3_below and above_vwap)

    # ── 2. ORB (5분 = 1봉 / 15분 = 3봉) ─────────────────
    orb5_high  = float(high.iloc[0])
    orb5_low   = float(low.iloc[0])
    orb15_high = float(high.iloc[:3].max()) if len(df) >= 3 else orb5_high
    orb15_low  = float(low.iloc[:3].min())  if len(df) >= 3 else orb5_low

    above_orb15_high = price > orb15_high
    orb15_low_broken = price < orb15_low
    orb5_low_broken  = price < orb5_low

    # Fakeout: ORB High 돌파 후 다시 박스 안으로
    above_orb_at_any = (high > orb15_high).any()
    fakeout = bool(above_orb_at_any and not above_orb15_high and
                   price < orb15_high * 0.995)

    # ── 3. Volume Pace ────────────────────────────────────
    cum_vol        = float(volume.sum())
    elapsed_bars   = len(df)
    elapsed_frac   = min(elapsed_bars * 5 / 390, 1.0)   # 390분 = 1 trading day
    projected_vol  = (cum_vol / elapsed_frac) if elapsed_frac > 0 else cum_vol
    volume_pace    = round(projected_vol / avg_daily_vol, 2) if avg_daily_vol > 0 else 0

    # Volume fade: 마지막 3봉 거래량이 평균 intraday 봉 거래량보다 모두 낮음
    avg_bar_vol  = float(volume.mean())
    last3_vols   = volume.iloc[-3:].values if len(df) >= 3 else volume.values
    volume_fade  = bool((last3_vols < avg_bar_vol * 0.5).all())
    volume_surge = bool((last3_vols > avg_bar_vol * 1.5).any())

    # ── 4. 고점/저점 구조 ────────────────────────────────
    day_high = float(high.max())
    day_low  = float(low.min())

    higher_low_count, lower_high_count = _count_hl_lh(high, low)

    # 고점 대비 현재가 하락률
    from_high_pct = round((price - day_high) / day_high * 100, 2) if day_high else 0

    # Intraday 종가 위치: (현재가 - 당일저점) / (당일고점 - 당일저점)
    day_range       = day_high - day_low
    close_position  = round((price - day_low) / day_range, 3) if day_range > 0 else 0.5

    # ── 5. Entry Score ────────────────────────────────────
    score_breakdown = {}

    # VWAP (25pts)
    vwap_pts = 0
    if above_vwap:              vwap_pts += 15
    if abs(vwap_dist_pct) <= 1: vwap_pts += 5
    if vwap_reclaim:            vwap_pts += 5
    if bars_above_vwap / max(total_bars, 1) >= 0.7:
        vwap_pts = min(vwap_pts + 3, 25)
    score_breakdown["vwap"] = min(vwap_pts, 25)

    # ORB (25pts)
    orb_pts = 0
    if not orb15_low_broken:   orb_pts += 10
    if above_orb15_high:       orb_pts += 15
    elif not orb15_low_broken: orb_pts += 5   # 박스 안 횡보, 저점은 유지
    if fakeout:                orb_pts = max(orb_pts - 8, 0)
    score_breakdown["orb"] = min(orb_pts, 25)

    # Volume Pace (20pts)
    if   volume_pace >= 5: vol_pts = 20
    elif volume_pace >= 3: vol_pts = 15
    elif volume_pace >= 2: vol_pts = 10
    elif volume_pace >= 1.5: vol_pts = 5
    else:                  vol_pts = 0
    if volume_fade:  vol_pts = max(vol_pts - 8, 0)
    if volume_surge: vol_pts = min(vol_pts + 3, 20)
    score_breakdown["volume"] = vol_pts

    # Structure (20pts)
    struct_pts = min(higher_low_count * 5, 15)
    if lower_high_count == 0:  struct_pts += 5
    elif lower_high_count >= 2: struct_pts = max(struct_pts - 5, 0)
    score_breakdown["structure"] = min(struct_pts, 20)

    # Close Position (10pts)
    if   close_position >= 0.8: pos_pts = 10
    elif close_position >= 0.6: pos_pts = 7
    elif close_position >= 0.4: pos_pts = 4
    else:                       pos_pts = 0
    score_breakdown["position"] = pos_pts

    entry_score = round(sum(score_breakdown.values()), 1)

    # ── 6. State Machine ─────────────────────────────────
    failed_reasons = []

    # FAILED 조건
    if orb15_low_broken and not vwap_reclaim:
        failed_reasons.append("ORB 15분 저점 이탈")
    if from_high_pct <= -20:
        failed_reasons.append(f"고점 대비 {from_high_pct:.1f}% 급락")
    if bars_below_vwap / max(total_bars, 1) >= 0.6 and not above_vwap:
        failed_reasons.append(f"VWAP 아래 {bars_below_vwap}봉 지속")
    if lower_high_count >= 2 and higher_low_count == 0:
        failed_reasons.append("Lower High 2회 이상, Higher Low 없음")
    if volume_fade and entry_score < 30:
        failed_reasons.append("거래량 급감 + 구조 약화")

    # 상태 결정
    if failed_reasons:
        engine_status = "FAILED"
        reason = "실패 조건: " + " | ".join(failed_reasons)

    elif (opp_score >= 65 and entry_score >= 65
          and above_vwap and not orb15_low_broken
          and higher_low_count >= 2 and volume_pace >= 2):
        engine_status = "BUYABLE"
        signals_str   = _top_signals(above_vwap, vwap_dist_pct, above_orb15_high, volume_pace, higher_low_count)
        reason        = f"진입 조건 충족 — {signals_str}"

    elif (entry_score < 40
          and (not above_vwap or lower_high_count >= 2 or volume_fade)):
        engine_status = "WEAKENING"
        reason = "신호 약화: VWAP 이탈 / 거래량 감소 / Lower High 형성"

    elif (above_vwap and not orb15_low_broken and
          (higher_low_count >= 1 or volume_pace >= 1.5)):
        engine_status = "SETTING_UP"
        reason = "구조 형성 중 — 진입 조건 접근"

    else:
        engine_status = "WATCH"
        reason = "관망 — 추가 확인 필요"

    signals = {
        "price":              price,
        "vwap":               round(vwap, 2),
        "vwap_distance_pct":  vwap_dist_pct,
        "above_vwap":         above_vwap,
        "vwap_reclaim":       vwap_reclaim,
        "bars_above_vwap":    bars_above_vwap,
        "bars_below_vwap":    bars_below_vwap,
        "orb_5_high":         round(orb5_high, 2),
        "orb_5_low":          round(orb5_low, 2),
        "orb_15_high":        round(orb15_high, 2),
        "orb_15_low":         round(orb15_low, 2),
        "above_orb_15_high":  above_orb15_high,
        "orb_15_low_broken":  orb15_low_broken,
        "fakeout":            fakeout,
        "volume_pace":        volume_pace,
        "volume_fade":        volume_fade,
        "volume_surge":       volume_surge,
        "higher_low_count":   higher_low_count,
        "lower_high_count":   lower_high_count,
        "day_high":           round(day_high, 2),
        "day_low":            round(day_low, 2),
        "from_high_pct":      from_high_pct,
        "close_position":     close_position,
    }

    from datetime import datetime as _dt
    transition_entry = {
        "time":         _dt.now().strftime("%m/%d %H:%M"),
        "status":       engine_status,
        "entry_score":  entry_score,
        "reason":       reason,
    }

    return {
        "entry_score":      entry_score,
        "engine_status":    engine_status,
        "reason":           reason,
        "failed_reasons":   failed_reasons,
        "signals":          signals,
        "score_breakdown":  score_breakdown,
        "transition_entry": transition_entry,
    }


# ── 헬퍼 ─────────────────────────────────────────────────

def _count_hl_lh(high: pd.Series, low: pd.Series) -> tuple[int, int]:
    """
    Pivot 기반 Higher Low / Lower High 카운트.
    좌우 2봉 기준 피벗 저점/고점을 찾고 연속 비교.

    5분봉 하루치(~78봉) 기준 pivot_window=2가 적절:
    window=3이면 하루에 피벗을 거의 못 찾는 문제 발생.
    """
    lows  = low.values
    highs = high.values
    W = 2  # 좌우 N봉

    # 피벗 저점 리스트
    pivot_lows = [
        lows[i]
        for i in range(W, len(lows) - W)
        if all(lows[i] <= lows[i - j] for j in range(1, W + 1)) and
           all(lows[i] <= lows[i + j] for j in range(1, W + 1))
    ]

    # 피벗 고점 리스트
    pivot_highs = [
        highs[i]
        for i in range(W, len(highs) - W)
        if all(highs[i] >= highs[i - j] for j in range(1, W + 1)) and
           all(highs[i] >= highs[i + j] for j in range(1, W + 1))
    ]

    # 연속 피벗 저점 비교 → Higher Low
    hl_count = sum(
        1 for i in range(1, len(pivot_lows))
        if pivot_lows[i] > pivot_lows[i - 1]
    )

    # 연속 피벗 고점 비교 → Lower High
    lh_count = sum(
        1 for i in range(1, len(pivot_highs))
        if pivot_highs[i] < pivot_highs[i - 1]
    )

    return hl_count, lh_count


def _top_signals(above_vwap, vwap_dist, above_orb, vol_pace, hl_count) -> str:
    parts = []
    if above_vwap:
        parts.append(f"VWAP 위 +{vwap_dist:.1f}%")
    if above_orb:
        parts.append("ORB 돌파")
    if vol_pace >= 2:
        parts.append(f"Volume Pace {vol_pace:.1f}x")
    if hl_count >= 2:
        parts.append(f"Higher Low {hl_count}회")
    return ", ".join(parts) if parts else "복합 조건 충족"


def _empty_result() -> dict:
    return {
        "entry_score":     0,
        "engine_status":   "WATCH",
        "reason":          "-",
        "failed_reasons":  [],
        "signals":         {},
        "score_breakdown": {"vwap": 0, "orb": 0, "volume": 0, "structure": 0, "position": 0},
    }
