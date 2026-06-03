"""
swing_screener/screener.py
Main orchestrator — 6-module screener with live yfinance data
"""

import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from data.price_loader      import get_price_data, get_ticker_info, get_market_data, get_premarket_data, FINNHUB_READY
from modules.indicators     import calculate_indicators
from modules.market_regime  import score_market
from modules.basic_filter   import pass_basic_filter, pass_momentum_filter
from modules.ignition       import score_ignition
from modules.supply_structure import score_supply
from modules.chart_structure  import detect_pattern, find_structural_stop
from modules.risk_plan      import calculate_trade_plan
from modules.scoring        import calculate_final_score
from modules.catalyst       import score_catalyst
from config                 import MARKET_ETFS, SECTOR_ETFS


def run_screener(tickers: list, verbose: bool = True) -> pd.DataFrame:

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print("\n" + "="*60)
    print(f"  SWING SCREENER  |  {now}")
    finnhub_status = "Finnhub connected (pre-market ON)" if FINNHUB_READY else "Finnhub not configured (EOD only)"
    print(f"  {finnhub_status}")
    print("="*60)

    # ── Step 1: Market Regime ─────────────────────────────────
    print("\n[1/6] Checking market regime...")
    market_data  = get_market_data(MARKET_ETFS)
    regime       = score_market(market_data)
    market_score = regime["market_score"]
    action       = regime["action"]
    loaded_etfs  = regime.get("loaded_etfs", [])

    print(f"  Market Score : {market_score} → {action}")
    print(f"  Loaded ETFs  : {loaded_etfs if loaded_etfs else 'NONE (check internet)'}")

    if regime.get("warning"):
        print(f"  ⚠️  {regime['warning']}")

    if market_score < 60:
        print(f"  ⚠️  Market score {market_score} < 60. No new entries recommended.")

    # QQQ 20d return for relative strength
    qqq_df = market_data.get("QQQ")
    qqq_ret_20d = 0
    if qqq_df is not None and len(qqq_df) >= 21:
        qqq_ret_20d = qqq_df["close"].iloc[-1] / qqq_df["close"].iloc[-21] - 1

    # ── Step 2: Screen tickers ────────────────────────────────
    print(f"\n[2/6] Screening {len(tickers)} tickers...")
    print("-" * 50)

    results   = []
    skipped   = []
    near_miss = []   # passed basic filter but failed later

    for i, ticker in enumerate(tickers):
        if verbose:
            print(f"  [{i+1:02d}/{len(tickers)}] {ticker:6s}...", end=" ", flush=True)

        df = get_price_data(ticker)
        if df is None:
            if verbose: print("SKIP (no data)")
            skipped.append(ticker)
            continue

        info = get_ticker_info(ticker)
        ind  = calculate_indicators(df)

        passed, reason = pass_basic_filter(info, ind)
        if not passed:
            if verbose: print(f"SKIP ({reason})")
            continue

        passed, reason = pass_momentum_filter(ind, qqq_ret_20d)
        if not passed:
            if verbose: print(f"SKIP ({reason})")
            near_miss.append({
                "Ticker":       ticker,
                "Failed_Stage": "Momentum Filter",
                "Reason":       reason,
                "Price":        ind["close"],
                "RVOL":         round(ind["rvol"], 2),
                "5D%":          f"{ind['ret_5d']:.1%}",
                "20D%":         f"{ind['ret_20d']:.1%}",
                "RS_QQQ":       f"{ind['ret_20d'] - qqq_ret_20d:.1%}",
                "Float_M":      round(info.get("float_shares", 0) / 1e6, 1),
                "Short%":       f"{info.get('short_pct_float', 0):.1%}",
                "Score":        None,
            })
            continue

        pm       = get_premarket_data(ticker)
        ignition = score_ignition(
            ind,
            pm_gap_pct      = pm.get("pm_gap_pct"),
            pm_volume_ratio = pm.get("pm_volume_ratio"),
        )
        catalyst = score_catalyst(ticker, ind)
        supply   = score_supply(info)
        chart    = detect_pattern(df, ind)
        pattern  = chart.get("pattern", "No Pattern")
        stop     = find_structural_stop(df, ind, pattern)
        plan     = calculate_trade_plan(ind["close"], stop, atr=ind.get("atr"))
        final    = calculate_final_score(
            market_score     = market_score,
            ignition_details = ignition,
            supply_details   = supply,
            chart_details    = chart,
            trade_plan       = plan,
            ind              = ind,
            qqq_ret_20d      = qqq_ret_20d,
            catalyst_score   = catalyst["catalyst_score"],
        )

        if verbose:
            grade = final["grade"]
            score = final["total_score"]
            ready = "✅ READY" if final["trade_ready"] else "👀 WATCH"
            print(f"{grade} ({score:4.1f}) | {pattern:25s} | RVOL:{ind['rvol']:.1f} | {ready}")

        score = final["total_score"]
        results.append({
            "Ticker":   ticker,
            "Price":    ind["close"],
            "Score":    score,
            "Grade":    final["grade"],
            "Pattern":  pattern,
            "RVOL":        ind["rvol"],
            "RVOL_3D":     ind.get("rvol_3d_avg"),
            "5D%":         f"{ind['ret_5d']:.1%}",
            "20D%":     f"{ind['ret_20d']:.1%}",
            "RS_QQQ":   f"{ind['ret_20d'] - qqq_ret_20d:.1%}",
            "Float_M":  round(info.get("float_shares", 0) / 1e6, 1),
            "Short%":   f"{info.get('short_pct_float', 0):.1%}",
            "PM_Gap%":       f"{pm['pm_gap_pct']:.1%}" if pm.get("pm_gap_pct") is not None else "-",
            "PM_VRatio":     pm.get("pm_volume_ratio") or "-",
            "Catalyst":       catalyst["catalyst_grade"],
            "EPS_Surp%":      catalyst.get("eps_surprise_pct"),
            "Earn_DaysAgo":   catalyst.get("earnings_days_ago"),
            "Next_Earn_Days": catalyst.get("next_earnings_days"),
            "ATR":            ind.get("atr"),
            "ATR_Stop":       plan.get("atr_stop"),
            "Entry":    plan.get("entry"),
            "Stop":     plan.get("stop"),
            "Target":   plan.get("target"),
            "Stop%":    f"{plan.get('stop_pct', 0):.1%}",
            "Shares":   plan.get("shares", 0),
            "Risk$":    plan.get("risk_dollars", 0),
            "Profit$":  plan.get("profit_dollars", 0),
            "R:R":      plan.get("rr", 0),
            "Ready":    "YES" if final["trade_ready"] else "NO",
            "TradeReason": plan.get("reason", ""),
            "Mkt_Sc":   final["breakdown"]["market"],
            "Ign_Sc":   final["breakdown"]["ignition"],
            "Qual_Sc":  final["breakdown"]["quality"],
            "Sup_Sc":   final["breakdown"]["supply"],
            "Chart_Sc": final["breakdown"]["chart"],
            "Risk_Sc":  final["breakdown"]["risk"],
        })

        if not final["trade_ready"]:
            fail_reasons = []
            if score < 75:
                fail_reasons.append(f"Score {score:.1f} < 75")
            if pattern == "No Pattern":
                fail_reasons.append("No chart pattern")
            if plan.get("rr", 0) < 1.8:
                fail_reasons.append(f"R:R {plan.get('rr',0)} < 1.8")
            if plan.get("stop_pct", 0) > 0.07:
                fail_reasons.append(f"Stop {plan.get('stop_pct',0):.1%} > 7%")
            near_miss.append({
                "Ticker":       ticker,
                "Failed_Stage": "Scoring",
                "Reason":       " | ".join(fail_reasons) if fail_reasons else plan.get("reason", ""),
                "Price":        ind["close"],
                "RVOL":         round(ind["rvol"], 2),
                "5D%":          f"{ind['ret_5d']:.1%}",
                "20D%":         f"{ind['ret_20d']:.1%}",
                "RS_QQQ":       f"{ind['ret_20d'] - qqq_ret_20d:.1%}",
                "Float_M":      round(info.get("float_shares", 0) / 1e6, 1),
                "Short%":       f"{info.get('short_pct_float', 0):.1%}",
                "Score":        score,
            })

    # ── Output ────────────────────────────────────────────────
    df_out = pd.DataFrame(results)

    os.makedirs("output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    if not df_out.empty:
        df_out = df_out.sort_values("Score", ascending=False).reset_index(drop=True)
        csv_path = f"output/watchlist_{timestamp}.csv"
        df_out.to_csv(csv_path, index=False)

    print("\n" + "="*60)
    print(f"  RESULTS  |  Market: {market_score} ({action})")
    print("="*60)

    if skipped:
        print(f"\n  ⚠️  {len(skipped)} tickers returned no data: {skipped[:5]}{'...' if len(skipped)>5 else ''}")
        print("     → Check internet connection or try: pip install yfinance --upgrade")

    if df_out.empty:
        print("\n  No candidates passed all filters today.")
        print("  Possible reasons:")
        print("    - Market is bearish (low market score)")
        print("    - Tickers don't meet momentum/volume criteria")
        print("    - yfinance connectivity issue (run screener_demo.py to verify logic)")
        return df_out

    ready_df = df_out[df_out["Ready"] == "YES"]
    print(f"\n  🟢 TRADE READY : {len(ready_df)}")
    print(f"  👀 WATCHLIST   : {len(df_out) - len(ready_df)}")

    # Show top results
    cols = ["Ticker", "Price", "Score", "Grade", "Pattern",
            "RVOL", "5D%", "RS_QQQ", "R:R", "Ready"]
    print("\n" + df_out[cols].head(10).to_string(index=False))

    if not df_out.empty:
        print(f"\n  Saved → {csv_path}")

    # ── Near-Miss Report ──────────────────────────────────────
    if near_miss:
        print("\n" + "="*60)
        print("  NEAR-MISS REPORT  (passed basic filter, eliminated later)")
        print("="*60)
        nm_df = pd.DataFrame(near_miss).sort_values(
            "Score", ascending=False, na_position="last"
        ).reset_index(drop=True)

        print(f"\n  {'#':<3} {'Ticker':<7} {'Stage':<20} {'Score':<7} {'RVOL':<6} "
              f"{'5D%':<7} {'RS_QQQ':<8} {'Float_M':<9} {'Short%':<7} Reason")
        print("  " + "-"*95)
        for i, row in nm_df.iterrows():
            score_str = f"{row['Score']:.1f}" if row["Score"] is not None else "  -  "
            print(f"  {i+1:<3} {row['Ticker']:<7} {row['Failed_Stage']:<20} {score_str:<7} "
                  f"{row['RVOL']:<6} {row['5D%']:<7} {row['RS_QQQ']:<8} "
                  f"{row['Float_M']:<9} {row['Short%']:<7} {row['Reason']}")

        today    = datetime.now().strftime("%Y%m%d")
        nm_path  = f"output/nearmiss_{today}.csv"
        nm_df.to_csv(nm_path, index=False)
        print(f"\n  Saved → {nm_path}")

    return df_out


def load_universe(path: str = "universe.txt") -> list:
    """Load tickers from a text file (one per line, # = comment)."""
    if not os.path.exists(path):
        print(f"  ⚠️  {path} not found — using built-in list")
        return ["UPST", "HIMS", "CELH", "MARA", "ACAD", "BEAM", "ARWR", "TGTX"]
    tickers = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                tickers.append(line.upper())
    return tickers


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Swing Screener")
    parser.add_argument("--universe", default="universe.txt",
                        help="Ticker list file (default: universe.txt)")
    parser.add_argument("--verbose", action="store_true",
                        help="Show per-ticker progress")
    args = parser.parse_args()

    tickers = load_universe(args.universe)
    print(f"  Universe: {len(tickers)} tickers from {args.universe}")
    result = run_screener(tickers, verbose=args.verbose)
