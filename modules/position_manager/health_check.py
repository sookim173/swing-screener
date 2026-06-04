"""
modules/position_manager/health_check.py
포지션 건강도 점수 계산 (100점 만점)

일봉 + 5분봉 데이터 기반.

항목별 배점 (합계 ~100):
  손절 위치   15  (필수 조건)
  VWAP 위    12
  RS 강도    12
  Higher Low 12
  EMA21 위    8  (스윙 추세)
  카탈리스트  10
  RVOL       8  (거래량 모멘텀)
  매수 압력   8
  EMA8 위     4  (단기 모멘텀)
  섹터 강도   5
  목표 여유   5
  캔들 품질   4
  ─────────── 103 → min(score, 100)

점수에 따른 판정:
  80+  → HOLD_TIGHT
  65+  → HOLD
  50+  → CAUTION
  50미만 → WEAK_EXIT 후보
"""


def calculate_health_score(
    pos: dict,
    daily_ind: dict,
    intraday_ind: dict,
    market_score: int,
    sector_strong: bool,
    catalyst_intact: bool,
) -> dict:
    """
    pos          : 보유 포지션 정보 (entry_price, structural_stop, etc.)
    daily_ind    : 일봉 indicators (indicators.py 결과)
    intraday_ind : 5분봉 indicators (intraday_data.py 결과)
    market_score : 현재 시장 점수
    sector_strong: 섹터 ETF 강세 여부
    catalyst_intact: 카탈리스트 훼손 없음 여부
    """

    score    = 0
    details  = {}
    reasons  = []

    entry   = pos["entry_price"]
    stop    = pos.get("current_stop", pos["structural_stop"])
    current = intraday_ind.get("current_price") or daily_ind.get("close", entry)

    # ── 1. 구조적 손절 위 (필수) ──────────────────────────────
    if current > stop:
        score += 15
        details["above_stop"] = True
    else:
        details["above_stop"] = False
        reasons.append("구조적 손절 아래")

    # ── 2. VWAP 위 ────────────────────────────────────────────
    if intraday_ind.get("above_vwap"):
        score += 12
        details["above_vwap"] = True
    else:
        details["above_vwap"] = False
        reasons.append("VWAP 아래")

    # ── 3. EMA21 위 (5분봉) — 스윙 추세 핵심 ────────────────
    if intraday_ind.get("above_ema21"):
        score += 8
        details["above_ema21"] = True
    else:
        details["above_ema21"] = False
        reasons.append("EMA21 아래 (스윙 추세 약화)")

    # ── 4. EMA8 위 (5분봉) — 단기 모멘텀 ────────────────────
    if intraday_ind.get("above_ema8"):
        score += 4
        details["above_ema8"] = True
    else:
        details["above_ema8"] = False
        # EMA21 위면 단순 단기 조정으로 해석 → reason 생략

    details["ema_score"] = (8 if details["above_ema21"] else 0) + (4 if details["above_ema8"] else 0)

    # ── 5. Higher Low 유지 (5분봉) ───────────────────────────
    if intraday_ind.get("higher_low_5m"):
        score += 12
        details["higher_low"] = True
    else:
        details["higher_low"] = False
        reasons.append("Higher Low 깨짐")

    # ── 6. RVOL (일봉) — 거래량 모멘텀 ──────────────────────
    rvol = daily_ind.get("rvol", 0)
    if rvol >= 2.0:
        score += 8
        details["rvol_ok"] = True
    elif rvol >= 1.0:
        score += 5
        details["rvol_ok"] = True
    else:
        score += 0
        details["rvol_ok"] = False
        reasons.append(f"거래량 부족 (RVOL {rvol:.1f}x)")

    # ── 7. 상승일 거래량 증가 / 하락일 거래량 감소 ──────────────
    if intraday_ind.get("buying_pressure"):
        score += 8
        details["buying_pressure"] = True
    else:
        details["buying_pressure"] = False
        reasons.append("매수 압력 약함")

    # ── 8. 윗꼬리 없음 (매도 압력 없음) ─────────────────────────
    wick = intraday_ind.get("upper_wick_ratio", 0)
    if wick < 0.3:
        score += 4
        details["clean_candle"] = True
    elif wick > 0.6:
        reasons.append(f"윗꼬리 과다 ({wick:.0%})")
        details["clean_candle"] = False
    else:
        details["clean_candle"] = True

    # ── 9. 상대강도 vs QQQ (일봉) ────────────────────────────
    ret_20d    = daily_ind.get("ret_20d", 0)
    qqq_ret    = pos.get("qqq_ret_at_entry", 0)
    rs_current = ret_20d - qqq_ret
    if rs_current > 0:
        score += 12
        details["rs_strong"] = True
    else:
        details["rs_strong"] = False
        reasons.append("QQQ 대비 상대강도 약화")

    # ── 10. 카탈리스트 훼손 없음 ─────────────────────────────
    if catalyst_intact:
        score += 10
        details["catalyst_intact"] = True
    else:
        details["catalyst_intact"] = False
        reasons.append("카탈리스트 훼손")

    # ── 11. 섹터 강도 유지 ───────────────────────────────────
    if sector_strong:
        score += 5
        details["sector_strong"] = True
    else:
        details["sector_strong"] = False
        reasons.append("섹터 약화")

    # ── 12. 목표까지 공간 ────────────────────────────────────
    target      = pos.get("initial_target", entry * 1.15)
    pct_to_tgt  = (target - current) / current if current > 0 else 0
    if pct_to_tgt >= 0.05:
        score += 5
        details["room_to_target"] = True
    else:
        details["room_to_target"] = False
        reasons.append("목표까지 여유 부족")

    score = min(score, 100)

    # ── 판정 ─────────────────────────────────────────────────
    if score >= 80:
        grade = "HOLD_TIGHT"
    elif score >= 65:
        grade = "HOLD"
    elif score >= 50:
        grade = "CAUTION"
    else:
        grade = "WEAK_EXIT"

    return {
        "health_score": score,
        "health_grade": grade,
        "health_reasons": reasons,
        "health_details": details,
    }
