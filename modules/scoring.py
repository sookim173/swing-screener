"""
modules/scoring.py
Aggregates all module scores into final score (100pts)
6-Module Framework: Market, Ignition, Quality, Supply, Chart, Risk

1주일 스윙 매매 기준 비중 (선별 → 진입 분리 원칙):
  Market Regime   10pts  — 시장 허가증
  Ignition/RVOL   25pts  — 지금 돈이 들어오는가 (가장 중요)
  Catalyst        20pts  — 왜 오르는가
  Supply          20pts  — 얼마나 움직일 수 있는가 (Float+Short)
  Chart           15pts  — 어디서 들어갈 것인가 (진입 타이밍)
  Risk/Trade      10pts  — R:R 검증
"""

from config import SCORE_A, SCORE_B, SCORE_C, MARKET_SCORE_TRADE


def calculate_final_score(
    market_score: int,
    ignition_details: dict,
    supply_details: dict,
    chart_details: dict,
    trade_plan: dict,
    ind: dict,
    qqq_ret_20d: float = 0,
    catalyst_score: int = 0,     # Day 3 - news/earnings quality
) -> dict:

    breakdown = {}

    # ── 1. Market Regime (10pts) ──────────────────────────────
    mkt = min(market_score / 100 * 10, 10)
    breakdown["market"] = round(mkt, 1)

    # ── 2. Ignition (25pts) ───────────────────────────────────
    ign_raw = ignition_details.get("ignition_score", 0)
    ign = min(ign_raw / 40 * 25, 25)
    breakdown["ignition"] = round(ign, 1)

    # ── 3. Quality / Catalyst (20pts) ────────────────────────
    # Day 1: basic relative strength proxy
    # Day 3: real catalyst score from news/earnings
    if catalyst_score > 0:
        qual = min(catalyst_score / 50 * 20, 20)
    else:
        # Basic: relative strength vs QQQ + momentum
        rs = ind.get("ret_20d", 0) - qqq_ret_20d
        rs_score = 10 if rs > 0.10 else 7 if rs > 0.05 else 4 if rs > 0 else 0
        mom_score = 5 if ind.get("ret_5d", 0) > 0.08 else 3 if ind.get("ret_5d", 0) > 0.05 else 1
        qual = min(rs_score + mom_score, 20)
    breakdown["quality"] = round(qual, 1)

    # ── 4. Supply Structure (20pts) ──────────────────────────
    # Float + Short Interest: 움직임의 물리적 한계 결정
    # Float 200M+ 종목은 카탈리스트가 있어도 1주일 15% 어려움
    sup_raw = supply_details.get("supply_score", 0)
    sup = min(sup_raw / 28 * 20, 20)
    breakdown["supply"] = round(sup, 1)

    # ── 5. Chart Structure (15pts) ────────────────────────────
    # 선별 후 진입 타이밍 결정 — 선별 기준이 아닌 진입 기준
    chart_raw = chart_details.get("chart_score", 0)
    chart = min(chart_raw / 30 * 15, 15)
    breakdown["chart"] = round(chart, 1)

    # ── 6. Risk / Trade Plan (10pts) ─────────────────────────
    rr = trade_plan.get("rr", 0)
    stop_valid = trade_plan.get("trade_ready", False)
    stop_pct = trade_plan.get("stop_pct", 1)

    if stop_valid and rr >= 2.5:
        risk_pts = 10
    elif stop_valid and rr >= 2.0:
        risk_pts = 8
    elif stop_valid and rr >= 1.8:
        risk_pts = 6
    elif rr >= 1.5:
        risk_pts = 3
    else:
        risk_pts = 0
    breakdown["risk"] = risk_pts

    # ── Total ─────────────────────────────────────────────────
    total = sum(breakdown.values())
    total = round(min(total, 100), 1)

    if total >= SCORE_A:
        grade = "A"
    elif total >= SCORE_B:
        grade = "B"
    elif total >= SCORE_C:
        grade = "C"
    else:
        grade = "D"

    # Trade ready: score + market + trade plan all must pass
    trade_ready = (
        total >= SCORE_B and
        market_score >= MARKET_SCORE_TRADE and
        trade_plan.get("trade_ready", False)
    )

    return {
        "total_score": total,
        "grade": grade,
        "breakdown": breakdown,
        "trade_ready": trade_ready,
    }
