"""
screener_demo.py
Runs full 6-module screener using mock data (for logic verification).
Replace get_mock_data() with real API calls when running locally.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from data.mock_data        import get_mock_data, MOCK_UNIVERSE, make_price_series
from modules.indicators    import calculate_indicators
from modules.market_regime import score_market
from modules.basic_filter  import pass_basic_filter, pass_momentum_filter
from modules.ignition      import score_ignition
from modules.supply_structure import score_supply
from modules.chart_structure  import detect_pattern, find_structural_stop
from modules.risk_plan     import calculate_trade_plan
from modules.scoring       import calculate_final_score


def make_mock_market():
    """Simulate a healthy market (QQQ/SPY/IWM above 20MA, low VIX)"""
    def etf(trend):
        df = make_price_series(400, trend)
        return df
    return {
        "QQQ": etf(0.08),
        "SPY": etf(0.06),
        "IWM": etf(0.05),
        "^VIX": make_price_series(17, -0.05),
    }


def run_demo():
    print("\n" + "="*60)
    print("  SWING SCREENER — Day 1 MVP (Demo Mode)")
    print("="*60)

    # Market
    print("\n[1] Market Regime...")
    market_data = make_mock_market()
    from modules.market_regime import score_market
    regime = score_market(market_data)
    market_score = regime["market_score"]
    print(f"  Score: {market_score} → {regime['action']}")
    print(f"  QQQ above 20MA: {regime.get('qqq_above_ma20')} | VIX: {regime.get('vix_level')}")

    qqq_close = market_data["QQQ"]["close"]
    qqq_ret_20d = qqq_close.iloc[-1] / qqq_close.iloc[-21] - 1

    # Screen tickers
    print(f"\n[2] Screening {len(MOCK_UNIVERSE)} tickers...\n")
    results    = []
    near_miss  = []   # passed basic filter but failed later

    for ticker in MOCK_UNIVERSE:
        df, info = get_mock_data(ticker)
        if df is None:
            continue

        ind = calculate_indicators(df)

        passed, reason = pass_basic_filter(info, ind)
        if not passed:
            # Silently skip — didn't even meet basic liquidity/price criteria
            continue

        passed, reason = pass_momentum_filter(ind, qqq_ret_20d)
        if not passed:
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

        ignition = score_ignition(ind)
        supply   = score_supply(info)
        chart    = detect_pattern(df, ind)
        pattern  = chart.get("pattern", "No Pattern")
        stop     = find_structural_stop(df, ind, pattern)
        plan     = calculate_trade_plan(ind["close"], stop)
        final    = calculate_final_score(
            market_score=market_score,
            ignition_details=ignition,
            supply_details=supply,
            chart_details=chart,
            trade_plan=plan,
            ind=ind,
            qqq_ret_20d=qqq_ret_20d,
        )

        grade = final["grade"]
        score = final["total_score"]
        ready = "✅" if final["trade_ready"] else "👀"
        print(f"  {ticker:6s} | Score:{score:5.1f} ({grade}) | {pattern:25s} | RVOL:{ind['rvol']:.1f} | {ready}")

        row = {
            "Ticker":   ticker,
            "Price":    ind["close"],
            "Score":    score,
            "Grade":    grade,
            "Pattern":  pattern,
            "RVOL":     ind["rvol"],
            "5D%":      f"{ind['ret_5d']:.1%}",
            "20D%":     f"{ind['ret_20d']:.1%}",
            "RS_QQQ":   f"{ind['ret_20d']-qqq_ret_20d:.1%}",
            "Float_M":  round(info.get("float_shares",0)/1e6,1),
            "Short%":   f"{info.get('short_pct_float',0):.1%}",
            "Entry":    plan.get("entry"),
            "Stop":     plan.get("stop"),
            "Target":   plan.get("target"),
            "Stop%":    f"{plan.get('stop_pct',0):.1%}",
            "Shares":   plan.get("shares",0),
            "Risk$":    plan.get("risk_dollars",0),
            "Profit$":  plan.get("profit_dollars",0),
            "R:R":      plan.get("rr",0),
            "Ready":    "YES" if final["trade_ready"] else "NO",
            "TradeReason": plan.get("reason",""),
            "Mkt":      final["breakdown"]["market"],
            "Ign":      final["breakdown"]["ignition"],
            "Qual":     final["breakdown"]["quality"],
            "Sup":      final["breakdown"]["supply"],
            "Chart":    final["breakdown"]["chart"],
            "Risk":     final["breakdown"]["risk"],
        }
        results.append(row)

        # Track scored-but-not-ready as near miss with full detail
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

    df_out = pd.DataFrame(results).sort_values("Score", ascending=False).reset_index(drop=True)

    print("\n" + "="*60)
    print("  FINAL RESULTS")
    print("="*60)

    if df_out.empty:
        print("  No candidates passed filters.")
        return

    # Display table
    display_cols = ["Ticker","Price","Score","Grade","Pattern","RVOL",
                    "5D%","RS_QQQ","Float_M","Short%","Entry","Stop",
                    "Target","Stop%","R:R","Ready"]
    print("\n" + df_out[display_cols].to_string(index=False))

    print("\n── Score Breakdown ────────────────────────────────────")
    bk_cols = ["Ticker","Score","Mkt","Ign","Qual","Sup","Chart","Risk","Ready","TradeReason"]
    print(df_out[bk_cols].to_string(index=False))

    ready = df_out[df_out["Ready"]=="YES"]
    watch = df_out[df_out["Ready"]=="NO"]
    print(f"\n  🟢 TRADE READY : {len(ready)}")
    print(f"  👀 WATCHLIST   : {len(watch)}")

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

        nm_df.to_csv("output/nearmiss_demo.csv", index=False)
        print(f"\n  Saved → output/nearmiss_demo.csv")

    os.makedirs("output", exist_ok=True)
    df_out.to_csv("output/watchlist_demo.csv", index=False)
    print(f"\n  Saved → output/watchlist_demo.csv")

if __name__ == "__main__":
    run_demo()
