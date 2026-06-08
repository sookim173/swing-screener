"""
watchlist_engine.py
Alpaca 기반 실시간 Watchlist Engine

구조:
  Screener (15~30분) → Watchlist 등록
  Watchlist Engine (1분마다) → Entry Validation → 상태머신
  상태: WATCH → SETTING_UP → BUYABLE / WEAKENING → FAILED

실행:
  python watchlist_engine.py --tickers ALOY AAPL TSLA
  python watchlist_engine.py --tickers ALOY --interval 60
"""

import argparse
import time
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data.alpaca_loader       import get_multi_bars, get_live_price, ALPACA_READY
from modules.entry_validator  import validate_entry

# ── 설정 ──────────────────────────────────────────────────
DEFAULT_INTERVAL  = 60        # 초 (1분)
AVG_DAILY_VOL_MAP = {}        # ticker → avg daily vol (없으면 0)
OPP_SCORE_MAP     = {}        # ticker → opportunity score (없으면 50)

# 상태 변화 이력
_state_log: dict[str, list] = {}   # ticker → [{"time", "status", "score", "reason"}]
_prev_status: dict[str, str] = {}  # ticker → 마지막 status


# ── 포맷 헬퍼 ─────────────────────────────────────────────

STATUS_ICON = {
    "BUYABLE":    "🟢",
    "SETTING_UP": "🟡",
    "WATCH":      "⚪",
    "WEAKENING":  "🟠",
    "FAILED":     "🔴",
}


def _fmt_breakdown(bk: dict) -> str:
    parts = [
        f"VWAP:{bk.get('vwap',0)}",
        f"ORB:{bk.get('orb',0)}",
        f"Vol:{bk.get('volume',0)}",
        f"Struct:{bk.get('structure',0)}",
        f"Pivot:{bk.get('pivot_distance',0)}",
    ]
    return "  |  ".join(parts)


def _print_status(ticker: str, result: dict, changed: bool):
    now    = datetime.now().strftime("%H:%M:%S")
    status = result["engine_status"]
    score  = result["entry_score"]
    icon   = STATUS_ICON.get(status, "⚪")
    sigs   = result.get("signals", {})
    price  = sigs.get("price", 0)
    vwap   = sigs.get("vwap", 0)
    vol    = sigs.get("volume_pace", 0)
    pivot  = sigs.get("pivot_dist_pct")
    bk     = result.get("score_breakdown", {})

    # 상태 변화 시 강조
    tag = " *** STATUS CHANGE ***" if changed else ""

    print(f"\n[{now}] {ticker}  {icon} {status}  Score:{score}/100{tag}")
    print(f"  Price:${price:.2f}  VWAP:${vwap:.2f}  VolPace:{vol:.1f}x", end="")
    if pivot is not None:
        print(f"  PivotDist:+{pivot:.1f}%", end="")
    print()
    print(f"  [{_fmt_breakdown(bk)}]")
    print(f"  {result.get('reason', '-')}")

    if status == "BUYABLE":
        hl = sigs.get("higher_low_count", 0)
        print(f"\n  *** BUYABLE SIGNAL ***")
        print(f"  Higher Low: {hl}회  |  Entry Zone: ${price*0.998:.2f}~${price*1.002:.2f}")
        print(f"  Stop: ${sigs.get('orb_15_low', price*0.97):.2f}")


# ── 메인 루프 ─────────────────────────────────────────────

def run_watchlist(tickers: list[str], interval: int = DEFAULT_INTERVAL):
    """
    메인 감시 루프.
    매 interval초마다 tickers의 1분봉을 Alpaca에서 받아
    Entry Validation → 상태머신을 돌린다.
    """
    if not ALPACA_READY:
        print("[ERROR] Alpaca API key not configured. Check .env")
        return

    print("=" * 60)
    print("Watchlist Engine  —  Alpaca Real-time")
    print(f"Tickers  : {', '.join(tickers)}")
    print(f"Interval : {interval}s")
    print("=" * 60)

    for t in tickers:
        _state_log[t]   = []
        _prev_status[t] = None

    iteration = 0

    while True:
        iteration += 1
        fetch_time = datetime.now().strftime("%H:%M:%S")
        print(f"\n{'─'*60}")
        print(f"Cycle #{iteration}  [{fetch_time}]  fetching {len(tickers)} tickers...")

        # 한 번의 API 호출로 전체 종목 1분봉 수신
        bars_map = get_multi_bars(tickers, timeframe="1m", hours_back=7.0)

        for ticker in tickers:
            df_1m = bars_map.get(ticker)

            if df_1m is None or df_1m.empty:
                print(f"  [{ticker}] No data (장 외 시간?)")
                continue

            avg_vol   = AVG_DAILY_VOL_MAP.get(ticker, 0)
            opp_score = OPP_SCORE_MAP.get(ticker, 50)

            result = validate_entry(df_1m, avg_daily_vol=avg_vol, opp_score=opp_score)

            # 상태 변화 감지
            cur_status  = result["engine_status"]
            prev_status = _prev_status.get(ticker)
            changed     = cur_status != prev_status

            _print_status(ticker, result, changed)

            if changed:
                _state_log[ticker].append({
                    "time":   fetch_time,
                    "status": cur_status,
                    "score":  result["entry_score"],
                    "reason": result.get("reason", ""),
                })
                _prev_status[ticker] = cur_status

        print(f"\nNext update in {interval}s  (Ctrl+C to stop)")

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\n--- Watchlist Engine stopped ---")
            _print_summary(tickers)
            break


def _print_summary(tickers: list[str]):
    """종료 시 상태 변화 히스토리 출력."""
    print("\n" + "=" * 60)
    print("State Transition Summary")
    print("=" * 60)
    for ticker in tickers:
        log = _state_log.get(ticker, [])
        print(f"\n{ticker}:")
        if not log:
            print("  (no state changes)")
        for entry in log:
            icon = STATUS_ICON.get(entry["status"], "⚪")
            print(f"  {entry['time']}  {icon} {entry['status']}  Score:{entry['score']}")
            print(f"          {entry['reason'][:70]}")


# ── Step 5 검증용: 단일 실행 테스트 ──────────────────────

def run_single_check(tickers: list[str]):
    """
    루프 없이 1회만 실행 — Watchlist Engine 연결 검증용.
    """
    if not ALPACA_READY:
        print("[ERROR] Alpaca API key not configured.")
        return

    print("=" * 60)
    print("Step 5: Watchlist Engine  —  Single Check")
    print("=" * 60)

    bars_map = get_multi_bars(tickers, timeframe="1m", hours_back=7.0)

    for ticker in tickers:
        df_1m = bars_map.get(ticker)
        print(f"\n[{ticker}]")

        if df_1m is None or df_1m.empty:
            print("  No data")
            continue

        print(f"  1분봉 수신: {len(df_1m)}개  "
              f"({df_1m.index[0].strftime('%H:%M')} ~ "
              f"{df_1m.index[-1].strftime('%H:%M')} UTC)")

        result = validate_entry(df_1m, avg_daily_vol=0, opp_score=50)

        status = result["engine_status"]
        score  = result["entry_score"]
        sigs   = result.get("signals", {})
        bk     = result.get("score_breakdown", {})
        icon   = STATUS_ICON.get(status, "⚪")

        print(f"  Status : {icon} {status}")
        print(f"  Score  : {score}/100")
        print(f"  Price  : ${sigs.get('price',0):.2f}  "
              f"VWAP: ${sigs.get('vwap',0):.2f}  "
              f"VolPace: {sigs.get('volume_pace',0):.1f}x")

        pivot = sigs.get("pivot_dist_pct")
        pivot_low = sigs.get("recent_pivot_low")
        if pivot is not None:
            print(f"  Pivot  : Low=${pivot_low:.2f}  Dist=+{pivot:.1f}%")

        print(f"  Breakdown: {_fmt_breakdown(bk)}")
        print(f"  Reason : {result.get('reason','-')}")

        # 상태머신 전이 이력
        transitions = result.get("transition_entry")
        if transitions:
            print(f"  Latest : [{transitions['time']}] {transitions['status']}")

    print("\nStep 5 complete — Alpaca + State Machine verified.")


# ── CLI ───────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Alpaca Watchlist Engine")
    parser.add_argument("--tickers",  nargs="+", default=["ALOY", "AAPL"],
                        help="감시할 종목 리스트")
    parser.add_argument("--interval", type=int, default=60,
                        help="갱신 주기(초), 기본 60")
    parser.add_argument("--once",     action="store_true",
                        help="1회만 실행 (검증용)")
    args = parser.parse_args()

    if args.once:
        run_single_check(args.tickers)
    else:
        run_watchlist(args.tickers, interval=args.interval)
