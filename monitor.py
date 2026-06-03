# -*- coding: utf-8 -*-
"""
monitor.py
판별 프로그램 — 보유 종목 포지션 상태 판별

실행:
  python monitor.py                   # positions.json 기준
  python monitor.py --positions my_positions.json

출력:
  터미널 요약 + output/monitor_YYYYMMDD_HHMM.csv
"""

import os
import sys
import json

# Windows 터미널 UTF-8 출력
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import argparse
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from data.price_loader      import get_price_data, get_market_data
from modules.indicators     import calculate_indicators
from modules.market_regime  import score_market
from config                 import MARKET_ETFS, SECTOR_ETFS

from modules.position_manager.intraday_data import get_intraday_df, calculate_intraday_indicators
from modules.position_manager.health_check  import calculate_health_score
from modules.position_manager.stop_tracker  import update_trailing_stop
from modules.position_manager.exit_rules    import decide_action


ACTION_EMOJI = {
    "NEWS_EXIT":    "[NEWS]  ",
    "STOP_EXIT":    "[STOP]  ",
    "WEAK_EXIT":    "[WEAK]  ",
    "TARGET_EXIT":  "[TARGET]",
    "PARTIAL_EXIT": "[PART]  ",
    "MOVE_STOP_UP": "[STOP+] ",
    "TIME_EXIT":    "[TIME]  ",
    "HOLD_TIGHT":   "[TIGHT] ",
    "HOLD":         "[HOLD]  ",
    "CAUTION":      "[WATCH] ",
}


def load_positions(path: str) -> list:
    if not os.path.exists(path):
        print(f"  ⚠️  {path} 없음 — positions.json을 먼저 작성하세요")
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_sector_strength(sector_etf: str) -> bool:
    """섹터 ETF가 20MA 위인지 확인."""
    try:
        df = get_price_data(sector_etf)
        if df is None or len(df) < 21:
            return True   # 데이터 없으면 패스
        ma20  = df["close"].rolling(20).mean().iloc[-1]
        return float(df["close"].iloc[-1]) > float(ma20)
    except Exception:
        return True


def get_recent_news(ticker: str) -> list:
    """Finnhub 최근 7일 뉴스. API 없으면 빈 리스트."""
    try:
        import finnhub
        api_key = os.getenv("FINNHUB_API_KEY", "")
        if not api_key:
            return []
        client    = finnhub.Client(api_key=api_key)
        today     = datetime.now()
        date_from = (today.replace(day=today.day - 7)).strftime("%Y-%m-%d")
        date_to   = today.strftime("%Y-%m-%d")
        return client.company_news(ticker, _from=date_from, to=date_to) or []
    except Exception:
        return []


def run_monitor(positions: list, verbose: bool = True) -> pd.DataFrame:

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print("\n" + "="*65)
    print(f"  POSITION MONITOR  |  {now}")
    print("="*65)

    if not positions:
        print("  보유 포지션 없음")
        return pd.DataFrame()

    # ── 시장 점수 ─────────────────────────────────────────────
    print("\n[1/2] 시장 상태 확인...")
    market_data  = get_market_data(MARKET_ETFS)
    market_info  = score_market(market_data)
    market_score = market_info.get("market_score", 50)
    action_label = market_info.get("action", "SELECTIVE")
    print(f"  Market Score: {market_score}  ({action_label})")

    # ── 포지션별 판별 ─────────────────────────────────────────
    print(f"\n[2/2] {len(positions)}개 포지션 판별 중...")
    print("-"*65)

    results = []

    for pos in positions:
        ticker = pos["ticker"]
        print(f"\n  [{ticker}]", end=" ", flush=True)

        # 일봉 데이터
        df_daily = get_price_data(ticker)
        if df_daily is None:
            print("일봉 데이터 없음 — SKIP")
            continue
        daily_ind = calculate_indicators(df_daily)

        # 5분봉 데이터
        df_5m       = get_intraday_df(ticker, interval="5m")
        intraday_ind = calculate_intraday_indicators(df_5m) if df_5m is not None else {
            "current_price": daily_ind["close"],
            "above_vwap":    daily_ind.get("above_vwap", False),
            "above_ema8":    daily_ind.get("above_ma20", False),
            "above_ema21":   daily_ind.get("above_ma50", False),
            "higher_low_5m": daily_ind.get("higher_low", False),
            "buying_pressure": True,
            "upper_wick_ratio": 0.0,
            "above_open_range": False,
        }

        # 섹터 강도
        sector_etf    = pos.get("sector_etf", "QQQ")
        sector_strong = get_sector_strength(sector_etf)

        # 뉴스
        news_list = get_recent_news(ticker)

        # Catalyst 상태 (뉴스 없으면 intact로 간주)
        catalyst_intact = len(news_list) == 0 or _catalyst_intact(news_list)

        # Stop 업데이트
        stop_result = update_trailing_stop(pos, intraday_ind, daily_ind)
        pos["current_stop"] = stop_result["new_stop"]   # 업데이트 반영
        unrealized_R        = stop_result["unrealized_R"]

        # Health Score
        health = calculate_health_score(
            pos           = pos,
            daily_ind     = daily_ind,
            intraday_ind  = intraday_ind,
            market_score  = market_score,
            sector_strong = sector_strong,
            catalyst_intact = catalyst_intact,
        )

        # 최종 액션
        decision = decide_action(
            pos             = pos,
            daily_ind       = daily_ind,
            intraday_ind    = intraday_ind,
            market_score    = market_score,
            sector_strong   = sector_strong,
            catalyst_intact = catalyst_intact,
            news_list       = news_list,
            health_result   = health,
        )

        action = decision["action"]
        emoji  = ACTION_EMOJI.get(action, "  ")
        current_price = intraday_ind.get("current_price") or daily_ind["close"]
        unrealized_pct = (current_price - pos["entry_price"]) / pos["entry_price"]

        print(f"{emoji} {action}")
        if verbose:
            print(f"      가격: ${current_price:.2f}  |  손익: {unrealized_pct:+.1%}  |  {unrealized_R:+.1f}R")
            print(f"      Stop: ${pos['current_stop']:.2f}", end="")
            if stop_result["stop_moved"]:
                print(f"  ↑ ({stop_result['stop_reason']})", end="")
            print()
            print(f"      Health: {health['health_score']}/100 ({health['health_grade']})")
            print(f"      판단: {decision['reason']}")

        results.append({
            "Ticker":         ticker,
            "Action":         action,
            "Current":        current_price,
            "Entry":          pos["entry_price"],
            "PnL%":           f"{unrealized_pct:+.1%}",
            "R":              unrealized_R,
            "Days":           _holding_days_str(pos.get("entry_date")),
            "Health":         health["health_score"],
            "Stop":           pos["current_stop"],
            "Stop_Moved":     stop_result["stop_moved"],
            "Target":         pos.get("initial_target"),
            "Market_Score":   market_score,
            "Sector_Strong":  sector_strong,
            "VWAP":           intraday_ind.get("vwap"),
            "Above_VWAP":     intraday_ind.get("above_vwap"),
            "Above_EMA8":     intraday_ind.get("above_ema8"),
            "HH_5m":          intraday_ind.get("higher_high_5m"),
            "HL_5m":          intraday_ind.get("higher_low_5m"),
            "Reason":         decision["reason"],
        })

    # ── 결과 출력 ─────────────────────────────────────────────
    df_out = pd.DataFrame(results)

    print("\n" + "="*65)
    print("  SUMMARY")
    print("="*65)
    if not df_out.empty:
        for _, row in df_out.iterrows():
            emoji = ACTION_EMOJI.get(row["Action"], "  ")
            print(f"  {row['Ticker']:6s} | {emoji} {row['Action']:18s} | "
                  f"{row['PnL%']:>6s} ({row['R']:+.1f}R) | Stop ${row['Stop']:.2f}")

        os.makedirs("output", exist_ok=True)
        ts       = datetime.now().strftime("%Y%m%d_%H%M")
        csv_path = f"output/monitor_{ts}.csv"
        df_out.to_csv(csv_path, index=False)
        print(f"\n  [SAVED] {csv_path}")

    return df_out


# ── 헬퍼 ─────────────────────────────────────────────────────
def _catalyst_intact(news_list: list) -> bool:
    """뉴스 키워드 기반 카탈리스트 훼손 여부."""
    from modules.position_manager.exit_rules import NEGATIVE_KEYWORDS
    for item in news_list[:10]:
        text = ((item.get("headline") or "") + (item.get("summary") or "")).lower()
        if any(kw in text for kw in NEGATIVE_KEYWORDS):
            return False
    return True


def _holding_days_str(entry_date) -> str:
    from modules.position_manager.exit_rules import _holding_days
    d = _holding_days(entry_date)
    return f"Day {d}"


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Position Monitor")
    parser.add_argument("--positions", default="positions.json",
                        help="포지션 파일 (default: positions.json)")
    parser.add_argument("--verbose", action="store_true", default=True)
    args = parser.parse_args()

    positions = load_positions(args.positions)
    run_monitor(positions, verbose=args.verbose)
