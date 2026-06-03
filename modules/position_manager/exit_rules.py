"""
modules/position_manager/exit_rules.py
6단계 순서로 청산 판정

출력 액션:
  NEWS_EXIT          악재/오퍼링/위험공시
  STOP_EXIT          구조적 손절 이탈
  WEAK_EXIT          시장/섹터 악화 또는 약화 신호 누적
  TARGET_EXIT        목표 도달 전량 청산
  PARTIAL_EXIT       일부 익절
  MOVE_STOP_UP       손절선 상향
  TIME_EXIT          시간 손절
  HOLD_TIGHT         강한 winner 유지
  HOLD               정상 보유
  CAUTION            약화 경고, 주시
"""

from datetime import datetime, date


# ── 1단계: 긴급 뉴스 체크 ────────────────────────────────────
NEGATIVE_KEYWORDS = [
    "offering", "dilut", "s-3", "424b", "fda hold", "clinical hold",
    "sec invest", "restatement", "going concern", "bankruptcy",
    "delisting", "fraud", "resign", "ceo resign", "cfо resign",
    "secondary offering", "공매도", "상장폐지",
]

def check_news_risk(news_list: list) -> dict:
    """
    Finnhub company_news 결과에서 위험 키워드 탐지.
    news_list: [{"headline": "...", "datetime": ...}, ...]
    """
    if not news_list:
        return {"news_exit": False, "news_reason": ""}

    for item in news_list[:20]:   # 최근 20개만
        headline = (item.get("headline") or "").lower()
        summary  = (item.get("summary")  or "").lower()
        text     = headline + " " + summary

        for kw in NEGATIVE_KEYWORDS:
            if kw in text:
                return {
                    "news_exit":   True,
                    "news_reason": f"위험 키워드 감지: '{kw}' → {item.get('headline', '')[:80]}",
                }

    return {"news_exit": False, "news_reason": ""}


# ── 2단계: 손절 체크 ─────────────────────────────────────────
def check_stop(pos: dict, intraday_ind: dict, daily_ind: dict) -> dict:
    current      = intraday_ind.get("current_price") or daily_ind.get("close", 0)
    stop         = pos.get("current_stop", pos["structural_stop"])
    panic_stop   = stop * 0.98   # 구조적 손절보다 2% 추가 하락 = 즉시 청산

    if current <= panic_stop:
        return {"stop_exit": True, "stop_reason": f"Panic stop 이탈 (현재 {current:.2f} ≤ {panic_stop:.2f})"}

    close = daily_ind.get("close", current)
    if close < stop:
        return {"stop_exit": True, "stop_reason": f"종가 손절선 이탈 (종가 {close:.2f} < stop {stop:.2f})"}

    # VWAP + EMA8 동시 이탈 + 매도 압력 = Weak stop
    vwap_break = not intraday_ind.get("above_vwap", True)
    ema8_break = not intraday_ind.get("above_ema8", True)
    sell_pressure = not intraday_ind.get("buying_pressure", True)
    if vwap_break and ema8_break and sell_pressure:
        return {"stop_exit": True, "stop_reason": "VWAP + EMA8 이탈 + 매도 압력 동시 발생"}

    return {"stop_exit": False, "stop_reason": ""}


# ── 3단계: 시장/섹터 체크 ────────────────────────────────────
def check_market_risk(pos: dict, market_score: int, unrealized_R: float) -> dict:
    if market_score < 60:
        if unrealized_R < 1.0:
            return {"market_exit": True,
                    "market_reason": f"시장 점수 {market_score} < 60, 수익 1R 미달 → 정리"}
        else:
            return {"market_exit": False,
                    "market_reason": f"시장 점수 {market_score} < 60, 수익 중 → stop 상향"}
    return {"market_exit": False, "market_reason": ""}


# ── 4단계: 약화 신호 카운트 ──────────────────────────────────
def count_weak_signals(
    pos: dict,
    daily_ind: dict,
    intraday_ind: dict,
    market_score: int,
    sector_strong: bool,
) -> dict:
    signals = []
    current = intraday_ind.get("current_price") or daily_ind.get("close", 0)

    if not intraday_ind.get("above_vwap", True):
        signals.append("VWAP 아래 종가")
    if not intraday_ind.get("higher_low_5m", True):
        signals.append("Higher Low 깨짐")
    if intraday_ind.get("upper_wick_ratio", 0) > 0.5:
        signals.append(f"윗꼬리 과다 ({intraday_ind['upper_wick_ratio']:.0%})")
    if not intraday_ind.get("buying_pressure", True):
        signals.append("하락 거래량 > 상승 거래량")
    if daily_ind.get("ret_20d", 0) < pos.get("qqq_ret_at_entry", 0):
        signals.append("QQQ 대비 상대강도 하락")
    if not sector_strong:
        signals.append("섹터 ETF 약화")

    # 보유일 대비 수익 부족
    entry_date   = pos.get("entry_date")
    holding_days = _holding_days(entry_date)
    unrealized_R = (current - pos["entry_price"]) / pos["risk_per_share"] \
                   if pos.get("risk_per_share", 0) > 0 else 0
    if holding_days >= 3 and unrealized_R < 0.5:
        signals.append(f"{holding_days}일째 0.5R 미달")

    return {"weak_signals": signals, "weak_count": len(signals)}


# ── 5단계: 수익 관리 ─────────────────────────────────────────
def check_profit(
    pos: dict,
    intraday_ind: dict,
    daily_ind: dict,
    market_score: int,
    health_score: int,
) -> dict:
    entry   = pos["entry_price"]
    risk    = pos.get("risk_per_share", entry * 0.05)
    current = intraday_ind.get("current_price") or daily_ind.get("close", entry)
    target  = pos.get("initial_target", entry * 1.15)

    unrealized_return = (current - entry) / entry
    unrealized_R      = (current - entry) / risk if risk > 0 else 0
    close_near_high   = intraday_ind.get("above_open_range", False)

    result = {
        "unrealized_return": round(unrealized_return, 4),
        "unrealized_R":      round(unrealized_R, 2),
        "profit_action":     None,
        "profit_reason":     "",
    }

    # 목표 도달 (+10% 또는 2R)
    if unrealized_return >= 0.10 or unrealized_R >= 2.0:
        if close_near_high and market_score >= 75 and health_score >= 75:
            result["profit_action"] = "PARTIAL_EXIT"
            result["profit_reason"] = f"목표 도달 ({unrealized_return:.1%}) + 강한 종가 → 70% 청산, 30% runner"
        else:
            result["profit_action"] = "TARGET_EXIT"
            result["profit_reason"] = f"목표 도달 ({unrealized_return:.1%}) → 전량 청산"

    # 1.5R 도달 + 건강 점수 하락
    elif unrealized_R >= 1.5 and health_score < 70:
        result["profit_action"] = "PARTIAL_EXIT"
        result["profit_reason"] = f"1.5R 도달 + Health {health_score} < 70 → 50% 익절"

    # 1R 도달 → stop 올리기
    elif unrealized_R >= 1.0:
        result["profit_action"] = "MOVE_STOP_UP"
        result["profit_reason"] = f"1R 도달 ({unrealized_R:.1f}R) → Breakeven으로 stop 이동"

    return result


# ── 6단계: 시간 손절 ─────────────────────────────────────────
def check_time_stop(pos: dict, intraday_ind: dict, daily_ind: dict) -> dict:
    entry   = pos["entry_price"]
    risk    = pos.get("risk_per_share", entry * 0.05)
    current = intraday_ind.get("current_price") or daily_ind.get("close", entry)
    unrealized_R = (current - entry) / risk if risk > 0 else 0

    holding_days = _holding_days(pos.get("entry_date"))

    if holding_days >= 5 and unrealized_R < 1.0:
        return {"time_exit": True,
                "time_reason": f"{holding_days}일째 1R 미달 ({unrealized_R:.1f}R) → 시간 손절"}
    if holding_days >= 3 and unrealized_R < 0.5:
        return {"time_exit": True,
                "time_reason": f"{holding_days}일째 0.5R 미달 ({unrealized_R:.1f}R) → 모멘텀 소멸"}
    return {"time_exit": False, "time_reason": ""}


# ── 최종 판정 통합 ────────────────────────────────────────────
def decide_action(
    pos: dict,
    daily_ind: dict,
    intraday_ind: dict,
    market_score: int,
    sector_strong: bool,
    catalyst_intact: bool,
    news_list: list,
    health_result: dict,
) -> dict:
    """
    6단계 순서로 최종 액션 결정.
    """
    entry   = pos["entry_price"]
    risk    = pos.get("risk_per_share", entry * 0.05)
    current = intraday_ind.get("current_price") or daily_ind.get("close", entry)
    unrealized_R = (current - entry) / risk if risk > 0 else 0

    # 1. 긴급 뉴스
    news = check_news_risk(news_list)
    if news["news_exit"]:
        return _action("NEWS_EXIT", news["news_reason"], unrealized_R)

    # 2. 손절
    stop = check_stop(pos, intraday_ind, daily_ind)
    if stop["stop_exit"]:
        return _action("STOP_EXIT", stop["stop_reason"], unrealized_R)

    # 3. 시장 리스크
    mkt = check_market_risk(pos, market_score, unrealized_R)
    if mkt["market_exit"]:
        return _action("WEAK_EXIT", mkt["market_reason"], unrealized_R)

    health_score = health_result.get("health_score", 50)

    # 4. 수익 관리
    profit = check_profit(pos, intraday_ind, daily_ind, market_score, health_score)
    if profit["profit_action"]:
        return _action(profit["profit_action"], profit["profit_reason"], unrealized_R)

    # stop 업데이트 신호 (1R 이상)
    if unrealized_R >= 1.0 and not profit["profit_action"]:
        return _action("MOVE_STOP_UP",
                       f"1R+ ({unrealized_R:.1f}R) → stop 상향", unrealized_R)

    # 5. 시간 손절
    time = check_time_stop(pos, intraday_ind, daily_ind)
    if time["time_exit"]:
        return _action("TIME_EXIT", time["time_reason"], unrealized_R)

    # 6. 약화 신호
    weak = count_weak_signals(pos, daily_ind, intraday_ind, market_score, sector_strong)
    if weak["weak_count"] >= 3:
        return _action("WEAK_EXIT",
                       f"약화 신호 {weak['weak_count']}개: {', '.join(weak['weak_signals'][:3])}",
                       unrealized_R)

    # 건강도 기반 최종 판정
    grade = health_result.get("health_grade", "CAUTION")
    if grade == "HOLD_TIGHT":
        return _action("HOLD_TIGHT", "모멘텀 강함, 유지", unrealized_R)
    elif grade == "HOLD":
        return _action("HOLD", "구조 유지, 보유", unrealized_R)
    elif grade == "CAUTION":
        return _action("CAUTION", f"Health {health_score}/100 — 주시", unrealized_R)
    else:
        return _action("WEAK_EXIT",
                       f"Health {health_score} < 50 → 약화 청산", unrealized_R)


# ── 헬퍼 ─────────────────────────────────────────────────────
def _action(action: str, reason: str, unrealized_R: float) -> dict:
    return {
        "action":       action,
        "reason":       reason,
        "unrealized_R": round(unrealized_R, 2),
    }


def _holding_days(entry_date) -> int:
    if not entry_date:
        return 0
    try:
        if isinstance(entry_date, str):
            ed = datetime.strptime(entry_date, "%Y-%m-%d").date()
        else:
            ed = entry_date
        # 영업일 근사 (캘린더 일수 × 5/7)
        delta = (date.today() - ed).days
        return max(0, int(delta * 5 / 7))
    except Exception:
        return 0
