"""
dashboard.py  —  Swing Screener + Position Monitor 통합 대시보드
실행: streamlit run dashboard.py

탭 1: Screener   — 매일 후보 종목 선별
탭 2: Monitor    — 보유 포지션 판별
탭 3: Journal    — 과거 결과 조회
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import streamlit as st
import pandas as pd
from datetime import datetime, date

# ── Page config ──────────────────────────────────────────
st.set_page_config(
    page_title  = "Swing Screener",
    page_icon   = "chart_with_upwards_trend",
    layout      = "wide",
    initial_sidebar_state = "expanded",
)

# ── Custom CSS ────────────────────────────────────────────
st.markdown("""
<style>
.action-NEWS_EXIT    { background:#7f0000; color:white; padding:2px 8px; border-radius:4px; font-weight:bold; }
.action-STOP_EXIT    { background:#b71c1c; color:white; padding:2px 8px; border-radius:4px; font-weight:bold; }
.action-WEAK_EXIT    { background:#e65100; color:white; padding:2px 8px; border-radius:4px; font-weight:bold; }
.action-TIME_EXIT    { background:#f57f17; color:white; padding:2px 8px; border-radius:4px; }
.action-TARGET_EXIT  { background:#1b5e20; color:white; padding:2px 8px; border-radius:4px; font-weight:bold; }
.action-PARTIAL_EXIT { background:#2e7d32; color:white; padding:2px 8px; border-radius:4px; }
.action-MOVE_STOP_UP { background:#1565c0; color:white; padding:2px 8px; border-radius:4px; }
.action-HOLD_TIGHT   { background:#0d47a1; color:white; padding:2px 8px; border-radius:4px; font-weight:bold; }
.action-HOLD         { background:#1976d2; color:white; padding:2px 8px; border-radius:4px; }
.action-CAUTION      { background:#6d4c41; color:white; padding:2px 8px; border-radius:4px; }

/* Signal chip grid */
.sig-chip {
    display:inline-block; padding:3px 10px; border-radius:12px;
    font-size:0.78rem; font-weight:600; margin:2px;
}
.sig-ok   { background:#1b5e2044; border:1px solid #2e7d32; color:#81c784; }
.sig-warn { background:#b71c1c33; border:1px solid #c62828; color:#ef9a9a; }

/* Section divider */
.sec-label {
    font-size:0.72rem; font-weight:700; letter-spacing:.08em;
    color:#888; text-transform:uppercase; margin:8px 0 4px 0;
}
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════

def load_universe(path: str) -> list:
    if not os.path.exists(path):
        return []
    tickers = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                tickers.append(line.upper())
    return tickers


def grade_color(grade: str) -> str:
    return {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴"}.get(str(grade)[0], "⚪")


def action_badge(action: str) -> str:
    labels = {
        "NEWS_EXIT":    "🚨 NEWS EXIT",
        "STOP_EXIT":    "🛑 STOP",
        "WEAK_EXIT":    "⚠️ WEAK EXIT",
        "TIME_EXIT":    "⏰ TIME EXIT",
        "TARGET_EXIT":  "🎯 TARGET",
        "PARTIAL_EXIT": "✂️ PARTIAL",
        "MOVE_STOP_UP": "📈 STOP UP",
        "HOLD_TIGHT":   "💪 HOLD TIGHT",
        "HOLD":         "✅ HOLD",
        "CAUTION":      "👀 CAUTION",
    }
    return labels.get(action, action)


def generate_ai_summary(row: dict) -> str:
    """
    포지션 데이터를 바탕으로 한 문단 요약을 생성.
    LLM 없이 규칙 기반으로 생성.
    """
    ticker   = row.get("Ticker", "")
    action   = row.get("Action", "HOLD")
    r_val    = row.get("R", 0)
    rs       = row.get("RS_vs_Sector", 0)
    rvol     = row.get("RVOL", 0)
    health   = row.get("Health", 0)
    trade_age = row.get("Trade_Age", 0)
    hd       = row.get("Health_Details") or {}
    weak     = row.get("Weak_Signals") or []
    remaining_rr = row.get("Remaining_RR", 0)

    strengths = []
    weaknesses = []

    # 강점 분석
    if rs > 5:
        strengths.append(f"강한 RS (+{rs:.0f}%, 섹터 대비 압도적 강세)")
    elif rs > 0:
        strengths.append(f"RS 양호 (+{rs:.0f}%)")
    if hd.get("above_vwap"):
        strengths.append("VWAP 위 거래 (수급 살아있음)")
    if hd.get("higher_low"):
        strengths.append("Higher Low 구조 유지")
    if hd.get("above_stop"):
        strengths.append(f"손절선 위 유지")
    if hd.get("catalyst_intact"):
        strengths.append("카탈리스트 훼손 없음")
    if hd.get("sector_strong"):
        strengths.append("섹터 강세")
    if rvol >= 2.0:
        strengths.append(f"거래량 강함 (RVOL {rvol:.1f}x)")
    if r_val >= 1.0:
        strengths.append(f"현재 {r_val:.1f}R 수익 중")

    # 약점 분석
    if rvol < 1.0:
        weaknesses.append(f"거래량 부족 (RVOL {rvol:.1f}x)")
    elif rvol < 1.5:
        weaknesses.append(f"거래량 보통 (RVOL {rvol:.1f}x)")
    if hd.get("ema_score", 10) < 10:
        weaknesses.append("EMA8/21 아래 위치")
    if rs < 0:
        weaknesses.append(f"RS 약화 ({rs:.0f}%)")
    if not hd.get("buying_pressure"):
        weaknesses.append("매수 압력 약함")
    if not hd.get("room_to_target"):
        weaknesses.append("목표까지 여유 부족")
    if trade_age >= 10:
        weaknesses.append(f"{trade_age}일째 보유 중 (횡보 점검 필요)")
    for sig in weak:
        if sig not in " ".join(weaknesses):
            weaknesses.append(sig)

    # 액션별 결론 문장
    if action in ("STOP_EXIT", "NEWS_EXIT"):
        conclusion = "손절 조건 충족 — 즉시 청산 필요."
    elif action == "WEAK_EXIT":
        conclusion = "약화 신호 누적 — 청산 또는 포지션 축소 고려."
    elif action == "TIME_EXIT":
        conclusion = f"{trade_age}일 보유 중 목표 도달 실패 — 시간 손절 고려."
    elif action in ("TARGET_EXIT", "PARTIAL_EXIT"):
        conclusion = "목표가 근접 또는 도달 — 익절 타이밍."
    elif action == "MOVE_STOP_UP":
        conclusion = f"{r_val:.1f}R 수익 중 — 손절선 상향으로 이익 보호."
    elif action == "HOLD_TIGHT":
        conclusion = f"남은 R:R {remaining_rr:.1f} 유지, 강한 구조 — 손절 고수하며 목표 보유."
    elif action == "HOLD":
        conclusion = f"손절선({row.get('Stop', '-')}) 미이탈, 구조 유지 — 보유 지속."
    else:  # CAUTION
        conclusion = "건강도 저하 신호 포착 — 손절선 확인 후 주시."

    # 문단 조합
    parts = []
    if strengths:
        parts.append("**강점:** " + ", ".join(strengths[:3]) + ".")
    if weaknesses:
        parts.append("**약점:** " + ", ".join(weaknesses[:3]) + ".")
    parts.append(f"**결론:** {conclusion}")

    return "  \n".join(parts)


POSITIONS_FILE = "positions.json"

def load_positions() -> list:
    if not os.path.exists(POSITIONS_FILE):
        return []
    try:
        with open(POSITIONS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_positions(positions: list):
    with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(positions, f, indent=2, ensure_ascii=False)


# ════════════════════════════════════════════════════════
#  TAB 1: SCREENER
# ════════════════════════════════════════════════════════

def run_screener_cached(tickers: list):
    from data.price_loader       import get_price_data, get_ticker_info, get_market_data, get_premarket_data
    from modules.indicators      import calculate_indicators
    from modules.market_regime   import score_market
    from modules.basic_filter    import pass_basic_filter, pass_momentum_filter
    from modules.ignition        import score_ignition
    from modules.supply_structure import score_supply
    from modules.chart_structure  import detect_pattern, find_structural_stop
    from modules.risk_plan       import calculate_trade_plan
    from modules.scoring         import calculate_final_score
    from modules.catalyst        import score_catalyst
    from config                  import MARKET_ETFS

    results = []
    near_miss = []

    market_data  = get_market_data(MARKET_ETFS)
    regime       = score_market(market_data)
    market_score = regime["market_score"]
    action       = regime["action"]

    qqq_df = market_data.get("QQQ")
    qqq_ret_20d = 0
    if qqq_df is not None and len(qqq_df) >= 21:
        qqq_ret_20d = qqq_df["close"].iloc[-1] / qqq_df["close"].iloc[-21] - 1

    progress = st.progress(0, text="Screening tickers...")
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        progress.progress((i + 1) / total, text=f"Screening {ticker} ({i+1}/{total})")

        df = get_price_data(ticker)
        if df is None:
            continue
        info = get_ticker_info(ticker)
        ind  = calculate_indicators(df)

        passed, reason = pass_basic_filter(info, ind)
        if not passed:
            continue

        passed, reason = pass_momentum_filter(ind, qqq_ret_20d)
        if not passed:
            near_miss.append({
                "Ticker": ticker, "Failed_Stage": "Momentum Filter",
                "Reason": reason, "Price": ind["close"],
                "RVOL": round(ind["rvol"], 2),
                "5D%": f"{ind['ret_5d']:.1%}", "20D%": f"{ind['ret_20d']:.1%}",
                "RS_QQQ": f"{ind['ret_20d'] - qqq_ret_20d:.1%}",
                "Float_M": round(info.get("float_shares", 0) / 1e6, 1),
                "Short%": f"{info.get('short_pct_float', 0):.1%}",
                "Score": None,
            })
            continue

        pm       = get_premarket_data(ticker)
        ignition = score_ignition(ind, pm.get("pm_gap_pct"), pm.get("pm_volume_ratio"))
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

        score = final["total_score"]
        results.append({
            "":             grade_color(final["grade"]),
            "Ticker":       ticker,
            "Grade":        final["grade"],
            "Score":        score,
            "Pattern":      pattern,
            "Price":        ind["close"],
            "RVOL":         round(ind["rvol"], 1),
            "RVOL_3D":      ind.get("rvol_3d_avg"),
            "5D%":          f"{ind['ret_5d']:+.1%}",
            "RS_QQQ":       f"{ind['ret_20d'] - qqq_ret_20d:+.1%}",
            "Float_M":      round(info.get("float_shares", 0) / 1e6, 1),
            "Short%":       f"{info.get('short_pct_float', 0):.0%}",
            "PM_Gap":       f"{pm['pm_gap_pct']:.1%}" if pm.get("pm_gap_pct") is not None else "-",
            "Catalyst":     catalyst["catalyst_grade"],
            "Next_Earn":    f"{catalyst.get('next_earnings_days')}d" if catalyst.get("next_earnings_days") is not None else "-",
            "ATR":          ind.get("atr"),
            "Entry":        plan.get("entry"),
            "Stop":         plan.get("stop"),
            "ATR_Stop":     plan.get("atr_stop"),
            "Target":       plan.get("target"),
            "R:R":          plan.get("rr"),
            "Ready":        "✅ YES" if final["trade_ready"] else "👀 NO",
            "Reason":       plan.get("reason", ""),
            "_Mkt":         final["breakdown"]["market"],
            "_Ign":         final["breakdown"]["ignition"],
            "_Qual":        final["breakdown"]["quality"],
            "_Sup":         final["breakdown"]["supply"],
            "_Chart":       final["breakdown"]["chart"],
            "_Risk":        final["breakdown"]["risk"],
            "_market_score": market_score,
            "_action":      action,
        })

        if not final["trade_ready"]:
            fail_reasons = []
            if score < 75: fail_reasons.append(f"Score {score:.1f} < 75")
            if pattern == "No Pattern": fail_reasons.append("No chart pattern")
            if plan.get("rr", 0) < 1.8: fail_reasons.append(f"R:R {plan.get('rr',0)} < 1.8")
            if plan.get("stop_pct", 0) > 0.07: fail_reasons.append(f"Stop {plan.get('stop_pct',0):.1%} > 7%")
            near_miss.append({
                "Ticker": ticker, "Failed_Stage": "Scoring",
                "Reason": " | ".join(fail_reasons) or plan.get("reason", ""),
                "Price": ind["close"], "RVOL": round(ind["rvol"], 2),
                "5D%": f"{ind['ret_5d']:.1%}", "20D%": f"{ind['ret_20d']:.1%}",
                "RS_QQQ": f"{ind['ret_20d'] - qqq_ret_20d:.1%}",
                "Float_M": round(info.get("float_shares", 0) / 1e6, 1),
                "Short%": f"{info.get('short_pct_float', 0):.1%}",
                "Score": score,
            })

    progress.empty()
    df_r = pd.DataFrame(results).sort_values("Score", ascending=False).reset_index(drop=True) if results else pd.DataFrame()
    df_n = pd.DataFrame(near_miss).sort_values("Score", ascending=False, na_position="last").reset_index(drop=True) if near_miss else pd.DataFrame()
    return df_r, df_n, market_score, action


def render_screener_tab():
    st.subheader("Screener")

    # Sidebar controls
    universe_file = st.sidebar.text_input("Universe file", value="universe_today.txt", key="univ_file")
    tickers = load_universe(universe_file)
    st.sidebar.caption(f"{len(tickers)} tickers loaded")
    run_btn = st.sidebar.button("▶  Run Screener", type="primary", use_container_width=True, key="run_screener")

    st.sidebar.markdown("---")
    st.sidebar.subheader("Load Previous Result")
    output_dir = "output"
    csv_files = []
    if os.path.exists(output_dir):
        csv_files = sorted(
            [f for f in os.listdir(output_dir) if f.startswith("watchlist_") and f.endswith(".csv")],
            reverse=True
        )[:20]
    selected_csv = st.sidebar.selectbox("CSV", ["— live run —"] + csv_files, key="sel_csv")

    if run_btn:
        if not tickers:
            st.error(f"No tickers found in {universe_file}")
        else:
            with st.spinner("Running screener..."):
                df_r, df_n, mkt, act = run_screener_cached(tickers)
            st.session_state.update({"sc_results": df_r, "sc_nearmiss": df_n,
                                     "sc_market": mkt, "sc_action": act})
            os.makedirs("output", exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            if not df_r.empty:
                df_r.to_csv(f"output/watchlist_{ts}.csv", index=False)
            if not df_n.empty:
                df_n.to_csv(f"output/nearmiss_{ts}.csv", index=False)

    elif selected_csv != "— live run —":
        try:
            df_r = pd.read_csv(f"output/{selected_csv}")
            st.session_state.update({"sc_results": df_r, "sc_nearmiss": pd.DataFrame(),
                                     "sc_market": "-", "sc_action": "Loaded from CSV"})
        except Exception as e:
            st.error(f"Failed to load: {e}")

    if "sc_results" not in st.session_state:
        st.info("Click **Run Screener** in the sidebar to start.")
        return

    df  = st.session_state["sc_results"]
    nm  = st.session_state.get("sc_nearmiss", pd.DataFrame())
    mkt = st.session_state.get("sc_market", "-")
    act = st.session_state.get("sc_action", "-")

    # Metric bar
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Market Score", f"{mkt}/100")
    c2.metric("Regime", act)
    ready_n = len(df[df["Ready"] == "✅ YES"]) if not df.empty and "Ready" in df.columns else 0
    c3.metric("Trade Ready", ready_n)
    c4.metric("Watch List", len(df) - ready_n if not df.empty else 0)
    st.markdown("---")

    if df.empty:
        st.info("No candidates passed all filters today.")
        return

    st.subheader("Candidates")
    display_cols = ["", "Ticker", "Grade", "Score", "Pattern", "Price",
                    "RVOL", "RVOL_3D", "5D%", "RS_QQQ", "Float_M", "Short%",
                    "PM_Gap", "Catalyst", "Next_Earn", "ATR",
                    "Entry", "Stop", "ATR_Stop", "Target", "R:R", "Ready"]
    display_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(
        df[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
            "R:R":   st.column_config.NumberColumn("R:R", format="%.2f"),
            "ATR":   st.column_config.NumberColumn("ATR", format="%.2f"),
        }
    )

    # Trade plan detail
    ready_df = df[df["Ready"] == "✅ YES"] if "Ready" in df.columns else pd.DataFrame()
    if not ready_df.empty:
        st.subheader("Trade Plan Detail")
        for _, row in ready_df.iterrows():
            with st.expander(f"{row['Ticker']}  |  {row['Pattern']}  |  Score {row['Score']:.1f}"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Entry",    f"${row['Entry']}")
                c2.metric("Stop",     f"${row['Stop']}")
                c3.metric("ATR Stop", f"${row.get('ATR_Stop', '-')}")
                c4.metric("Target",   f"${row['Target']}")

                bk_labels = ["Market","Ignition","Quality","Supply","Chart","Risk"]
                bk_cols   = ["_Mkt","_Ign","_Qual","_Sup","_Chart","_Risk"]
                bk_vals   = [row.get(c, 0) for c in bk_cols]
                bk_df = pd.DataFrame({"Module": bk_labels, "Score": bk_vals})
                st.bar_chart(bk_df.set_index("Module"))

                # Add to positions button
                if st.button(f"Add {row['Ticker']} to Positions", key=f"add_{row['Ticker']}"):
                    positions = load_positions()
                    existing  = [p["ticker"] for p in positions]
                    if row["Ticker"] not in existing:
                        risk = round(float(row["Entry"]) - float(row["Stop"]), 2)
                        positions.append({
                            "ticker":          row["Ticker"],
                            "entry_date":      date.today().isoformat(),
                            "entry_price":     float(row["Entry"]),
                            "shares":          0,
                            "structural_stop": float(row["Stop"]),
                            "current_stop":    float(row["Stop"]),
                            "initial_target":  float(row["Target"]),
                            "risk_per_share":  risk,
                            "pattern":         row.get("Pattern", ""),
                            "catalyst":        row.get("Catalyst", ""),
                            "sector_etf":      "QQQ",
                            "qqq_ret_at_entry": 0.0,
                        })
                        save_positions(positions)
                        st.success(f"{row['Ticker']} added to positions.json")
                    else:
                        st.warning(f"{row['Ticker']} already in positions")

    # Near-miss
    if nm is not None and not nm.empty:
        st.markdown("---")
        st.subheader("Near-Miss Report")
        st.caption("Passed basic filter but eliminated in later stages")
        st.dataframe(nm, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════
#  TAB 2: POSITION MONITOR
# ════════════════════════════════════════════════════════

def run_monitor_cached(positions: list):
    from data.price_loader      import get_price_data, get_market_data
    from modules.indicators     import calculate_indicators
    from modules.market_regime  import score_market
    from config                 import MARKET_ETFS
    from modules.position_manager.intraday_data import get_intraday_df, calculate_intraday_indicators
    from modules.position_manager.health_check  import calculate_health_score
    from modules.position_manager.stop_tracker  import update_trailing_stop, calculate_suggested_stops
    from modules.position_manager.exit_rules    import decide_action, _holding_days

    market_data  = get_market_data(MARKET_ETFS)
    market_info  = score_market(market_data)
    market_score = market_info.get("market_score", 50)

    results = []
    prog = st.progress(0, text="Evaluating positions...")

    for i, pos in enumerate(positions):
        ticker = pos["ticker"]
        prog.progress((i + 1) / len(positions), text=f"Evaluating {ticker}...")

        df_daily = get_price_data(ticker)
        if df_daily is None:
            continue
        daily_ind = calculate_indicators(df_daily)

        df_5m = get_intraday_df(ticker, "5m")
        if df_5m is not None:
            intraday_ind = calculate_intraday_indicators(df_5m)
        else:
            intraday_ind = {
                "current_price":   daily_ind["close"],
                "above_vwap":      daily_ind.get("above_vwap", False),
                "above_ema8":      daily_ind.get("above_ma20", False),
                "above_ema21":     daily_ind.get("above_ma50", False),
                "higher_low_5m":   daily_ind.get("higher_low", False),
                "higher_high_5m":  False,
                "buying_pressure": True,
                "upper_wick_ratio": 0.0,
                "above_open_range": False,
                "vwap": daily_ind["close"],
                "ema8": daily_ind.get("ma8", daily_ind["close"]),
                "ema21": daily_ind.get("ma20", daily_ind["close"]),
            }

        # Sector strength + RS 계산
        sector_etf = pos.get("sector_etf", "QQQ")
        sector_ret_20d = 0.0
        try:
            sec_df = get_price_data(sector_etf)
            if sec_df is not None and len(sec_df) >= 21:
                sector_strong  = float(sec_df["close"].iloc[-1]) > float(sec_df["close"].rolling(20).mean().iloc[-1])
                sector_ret_20d = float(sec_df["close"].iloc[-1] / sec_df["close"].iloc[-21] - 1)
            else:
                sector_strong = True
        except Exception:
            sector_strong = True

        # News
        news_list = _get_news(ticker)
        catalyst_intact = _catalyst_ok(news_list)

        # 자동 Stop/Target 계산
        suggested = calculate_suggested_stops(df_daily, daily_ind, intraday_ind, pos)

        # pos에 계산된 값 반영 (저장된 값이 0.01이면 자동 계산값으로 교체)
        if pos.get("structural_stop", 0) < pos["entry_price"] * 0.5:
            pos["structural_stop"] = suggested["suggested_stop"]
        if pos.get("current_stop", 0) < pos["entry_price"] * 0.5:
            pos["current_stop"] = suggested["suggested_stop"]
        if pos.get("risk_per_share", 0) <= 0.01:
            pos["risk_per_share"] = suggested["risk_per_share"]

        # Stop update (trailing)
        stop_result = update_trailing_stop(pos, intraday_ind, daily_ind)
        pos["current_stop"] = stop_result["new_stop"]

        health = calculate_health_score(
            pos=pos, daily_ind=daily_ind, intraday_ind=intraday_ind,
            market_score=market_score, sector_strong=sector_strong,
            catalyst_intact=catalyst_intact,
        )

        decision = decide_action(
            pos=pos, daily_ind=daily_ind, intraday_ind=intraday_ind,
            market_score=market_score, sector_strong=sector_strong,
            catalyst_intact=catalyst_intact, news_list=news_list,
            health_result=health,
        )

        current = intraday_ind.get("current_price") or daily_ind["close"]
        entry   = pos["entry_price"]
        risk    = pos.get("risk_per_share", suggested["risk_per_share"])
        pnl_pct = (current - entry) / entry

        # Trade Age
        trade_age = _holding_days(pos.get("entry_date"))

        # RS vs Sector ETF (20일 수익률 차이)
        ticker_ret_20d = daily_ind.get("ret_20d", 0)
        rs_vs_sector   = round((ticker_ret_20d - sector_ret_20d) * 100, 2)

        # Remaining R:R (현재가 기준 남은 보상/위험)
        target_price     = suggested["conservative_target"]
        remaining_reward = target_price - current
        remaining_risk   = current - pos["current_stop"]
        remaining_rr     = round(remaining_reward / remaining_risk, 2) if remaining_risk > 0 else 0
        remaining_upside = round(remaining_reward / current * 100, 2) if current > 0 else 0

        results.append({
            "Ticker":        ticker,
            "Action":        decision["action"],
            "Action_Label":  action_badge(decision["action"]),
            "Current":       round(current, 2),
            "Entry":         entry,
            "PnL%":          round(pnl_pct * 100, 2),
            "R":             decision["unrealized_R"],
            # ── 보완 1: Trade Age ─────────────────────────────
            "Trade_Age":     trade_age,
            "Entry_Date":    pos.get("entry_date", ""),
            # ── 보완 2: RVOL ──────────────────────────────────
            "RVOL":          daily_ind.get("rvol", 0),
            "RVOL_3d":       daily_ind.get("rvol_3d_avg", 0),
            "RVOL_5d":       daily_ind.get("rvol_5d_avg", 0),
            # ── ATR 값 + VWAP Distance ────────────────────────
            "ATR_Val":       suggested.get("atr", 0),
            "VWAP_Dist_Pct": round((intraday_ind.get("vwap", current) and
                             (current - intraday_ind.get("vwap", current)) /
                             intraday_ind.get("vwap", current) * 100), 2)
                             if intraday_ind.get("vwap") else 0,
            # ── EMA21 ─────────────────────────────────────────
            "Above_EMA21":   intraday_ind.get("above_ema21"),
            "EMA21_Val":     intraday_ind.get("ema21"),
            # ── 보완 3: RS vs Sector ──────────────────────────
            "RS_vs_Sector":  rs_vs_sector,
            "Sector_ETF":    sector_etf,
            "Ticker_Ret20d": round(ticker_ret_20d * 100, 2),
            "Sector_Ret20d": round(sector_ret_20d * 100, 2),
            # ── 보완 4: Remaining R:R ─────────────────────────
            "Remaining_RR":     remaining_rr,
            "Remaining_Upside": remaining_upside,
            # ── Health ────────────────────────────────────────
            "Health":        health["health_score"],
            "Health_Grade":  health["health_grade"],
            "Health_Details": health.get("health_details", {}),
            "Stop":               pos["current_stop"],
            "Stop_Moved":         stop_result["stop_moved"],
            "Stop_Reason":        stop_result["stop_reason"],
            # 자동 계산 Stop
            "Suggested_Stop":        suggested["suggested_stop"],
            "Suggested_Stop_Source": suggested.get("suggested_stop_source", "-"),
            "Structural_Stop":       suggested["structural_stop"],
            "ATR_Stop":              suggested["atr_stop"],
            "VWAP_Stop":             suggested["vwap_stop"],
            # 자동 계산 Target
            "RR_Target":          suggested["rr_target"],
            "ATR_Target":         suggested["atr_target"],
            "Resistance_Target":  suggested["resistance_target"],
            "Conservative_Target": target_price,
            "Suggested_RR":       suggested["suggested_rr"],
            "Target":             target_price,
            # ── 포지션 크기 + Risk $ ──────────────────────────
            "Shares":           pos.get("shares", 0),
            "Position_Value":   round(pos.get("shares", 0) * entry, 2),
            "Risk_Dollars":     round(pos.get("shares", 0) * risk, 2),
            "Risk_Pct_Account": round(pos.get("shares", 0) * risk / 1000 * 100, 2),
            # ── Exit signal 상세 ──────────────────────────────
            "Weak_Signals":  decision.get("weak_signals", []),
            "VWAP":          intraday_ind.get("vwap"),
            "Above_VWAP":    intraday_ind.get("above_vwap"),
            "Above_EMA8":    intraday_ind.get("above_ema8"),
            "HL_5m":         intraday_ind.get("higher_low_5m"),
            "HL_Prev_Low":   intraday_ind.get("prev_low_price"),
            "HL_Curr_Low":   intraday_ind.get("curr_low_price"),
            # ── Technical / News 상태 분리 ────────────────────
            "Technical_Grade": health["health_grade"],
            "News_Exit":       decision["action"] in {"NEWS_EXIT"},
            "News_Reason":     decision["reason"] if decision["action"] == "NEWS_EXIT" else "",
            "Market_Score":  market_score,
            "Sector_Strong": sector_strong,
            "Reason":        decision["reason"],
            "Health_Issues": " | ".join(health.get("health_reasons", [])),
        })

    prog.empty()
    save_positions(positions)   # stop 업데이트 저장
    return pd.DataFrame(results), market_score, market_info.get("action", "")


def _get_news(ticker: str) -> list:
    try:
        import finnhub
        api_key = os.getenv("FINNHUB_API_KEY", "")
        if not api_key:
            return []
        client    = finnhub.Client(api_key=api_key)
        today     = datetime.now()
        date_from = (today.replace(day=max(1, today.day - 7))).strftime("%Y-%m-%d")
        date_to   = today.strftime("%Y-%m-%d")
        return client.company_news(ticker, _from=date_from, to=date_to) or []
    except Exception:
        return []


def _catalyst_ok(news_list: list) -> bool:
    from modules.position_manager.exit_rules import NEGATIVE_KEYWORDS
    for item in news_list[:10]:
        text = ((item.get("headline") or "") + (item.get("summary") or "")).lower()
        if any(kw in text for kw in NEGATIVE_KEYWORDS):
            return False
    return True


def _action_color(action: str) -> str:
    exits  = {"NEWS_EXIT", "STOP_EXIT", "WEAK_EXIT", "TIME_EXIT"}
    profit = {"TARGET_EXIT", "PARTIAL_EXIT"}
    manage = {"MOVE_STOP_UP", "HOLD_TIGHT"}
    if action in exits:   return "🔴"
    if action in profit:  return "🟢"
    if action in manage:  return "🔵"
    return "🟡"


def render_monitor_tab():
    st.subheader("Position Monitor")

    positions = load_positions()

    # ── Add position form ────────────────────────────────
    with st.expander("➕ Add New Position", expanded=(len(positions) == 0)):
        with st.form("add_position"):
            c1, c2, c3 = st.columns(3)
            ticker      = c1.text_input("Ticker").upper().strip()
            entry_price = c2.number_input("Entry Price ($)", min_value=0.01, step=0.01)
            shares      = c3.number_input("Shares", min_value=1, step=1)

            c4, c5, c6 = st.columns(3)
            struct_stop = c4.number_input("Structural Stop ($) — 0 = 자동계산",
                                          min_value=0.0, step=0.01, value=0.0)
            target      = c5.number_input("Target ($) — 0 = 자동계산",
                                          min_value=0.0, step=0.01, value=0.0)
            sector_etf  = c6.selectbox("Sector ETF",
                            ["QQQ","XBI","SMH","IGV","XLF","XLE","XLI","CIBR","URA"])

            c7, c8 = st.columns(2)
            pattern  = c7.text_input("Pattern", value="Momentum Pullback")
            catalyst = c8.text_input("Catalyst", value="")

            st.caption("💡 Stop/Target을 0으로 두면 Run Monitor 실행 시 차트에서 자동 계산됩니다.")

            submitted = st.form_submit_button("Add Position", type="primary")
            if submitted and ticker and entry_price > 0:
                existing = [p["ticker"] for p in positions]
                if ticker in existing:
                    st.warning(f"{ticker} already exists")
                else:
                    risk = round(entry_price - struct_stop, 2) if struct_stop > 0 else entry_price * 0.05
                    positions.append({
                        "ticker":          ticker,
                        "entry_date":      date.today().isoformat(),
                        "entry_price":     entry_price,
                        "shares":          int(shares),
                        "structural_stop": struct_stop if struct_stop > 0 else 0.0,
                        "current_stop":    struct_stop if struct_stop > 0 else 0.0,
                        "initial_target":  target if target > 0 else 0.0,
                        "risk_per_share":  max(risk, 0.01),
                        "pattern":         pattern,
                        "catalyst":        catalyst,
                        "sector_etf":      sector_etf,
                        "qqq_ret_at_entry": 0.0,
                    })
                    save_positions(positions)
                    st.success(f"{ticker} added!")
                    st.rerun()

    if not positions:
        st.info("No positions yet. Add a position above or run the Screener and click 'Add to Positions'.")
        return

    # ── Current positions table ──────────────────────────
    st.markdown(f"**{len(positions)} open position(s)**")
    pos_preview = []
    for p in positions:
        pos_preview.append({
            "Ticker": p["ticker"],
            "Entry":  p["entry_price"],
            "Stop":   p["current_stop"],
            "Target": p.get("initial_target"),
            "Shares": p.get("shares", 0),
            "Pattern": p.get("pattern", ""),
            "Date":   p.get("entry_date", ""),
        })
    st.dataframe(pd.DataFrame(pos_preview), use_container_width=True, hide_index=True)

    # Delete position
    del_ticker = st.selectbox("Remove position", ["—"] + [p["ticker"] for p in positions])
    if del_ticker != "—":
        if st.button(f"Remove {del_ticker}", type="secondary"):
            positions = [p for p in positions if p["ticker"] != del_ticker]
            save_positions(positions)
            st.success(f"{del_ticker} removed")
            st.rerun()

    st.markdown("---")

    # ── Run monitor ──────────────────────────────────────
    run_mon = st.button("▶  Run Monitor", type="primary", use_container_width=True)

    if run_mon:
        with st.spinner("Evaluating positions..."):
            df_mon, mkt_score, mkt_action = run_monitor_cached(positions)
        st.session_state["mon_results"]      = df_mon
        st.session_state["mon_market_score"] = mkt_score
        st.session_state["mon_action"]       = mkt_action
        os.makedirs("output", exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        df_mon.to_csv(f"output/monitor_{ts}.csv", index=False)

    if "mon_results" not in st.session_state:
        return

    df  = st.session_state["mon_results"]
    mkt = st.session_state.get("mon_market_score", "-")
    act = st.session_state.get("mon_action", "-")

    if df.empty:
        st.warning("No results — check data connection.")
        return

    # Summary metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Market Score", f"{mkt}/100")
    c2.metric("Regime", act)
    exits  = len(df[df["Action"].str.contains("EXIT")])
    holds  = len(df[df["Action"].str.contains("HOLD")])
    c3.metric("Exit Signals", exits, delta=None)
    c4.metric("Hold", holds)

    st.markdown("---")

    # Results cards
    for _, row in df.iterrows():
        col_color = _action_color(row["Action"])
        pnl_sign  = "+" if row["PnL%"] >= 0 else ""
        trade_age = row.get("Trade_Age", 0)
        r_val     = row.get("R", 0)
        rr_left   = row.get("Remaining_RR", 0)
        hd        = row.get("Health_Details") or {}

        with st.expander(
            f"{col_color} **{row['Ticker']}**  |  "
            f"{action_badge(row['Action'])}  |  "
            f"Day {trade_age}  |  "
            f"P/L {pnl_sign}{row['PnL%']:.1f}%  ({r_val:+.2f}R)  |  "
            f"Health {row['Health']}/100",
            expanded=(row["Action"] not in {"HOLD", "CAUTION"})
        ):

            # ════ ROW 1: 핵심 숫자 ════════════════════════
            r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns(6)
            r1c1.metric("현재가",  f"${row['Current']:.2f}",
                        delta=f"{pnl_sign}{row['PnL%']:.1f}%")
            r1c2.metric("진입가",  f"${row['Entry']:.2f}")
            r1c3.metric("활성 손절",
                        f"${row['Stop']:.2f}",
                        delta=f"↑ {row['Stop_Reason']}" if row["Stop_Moved"] else
                              f"기준: {row.get('Suggested_Stop_Source','')}",
                        delta_color="normal" if row["Stop_Moved"] else "off")
            r1c4.metric("목표가",  f"${row.get('Conservative_Target', 0):.2f}",
                        delta=f"남은 상승 +{row.get('Remaining_Upside',0):.1f}%",
                        delta_color="normal")
            r1c5.metric("Current R", f"{r_val:+.2f}R",
                        delta="수익 중" if r_val > 0 else ("손실" if r_val < -0.5 else "진입 초기"),
                        delta_color="normal" if r_val > 0 else "inverse")
            r1c6.metric("남은 R:R",
                        f"{rr_left:.1f}:1" if rr_left > 0 else "-",
                        delta=f"Day {trade_age}" + (" ⚠ 횡보" if trade_age >= 10 else ""),
                        delta_color="inverse" if trade_age >= 10 else "off")

            # ════ ROW 2: 판정 3분할 + AI Summary ═════════
            tech_grade = row.get("Technical_Grade", "HOLD")
            news_exit  = row.get("News_Exit", False)
            tech_color = {"HOLD_TIGHT": "success", "HOLD": "success",
                          "CAUTION": "warning", "WEAK_EXIT": "error"}.get(tech_grade, "info")

            ts1, ts2, ts3 = st.columns([1, 1, 2])
            with ts1:
                st.markdown('<p class="sec-label">차트 상태</p>', unsafe_allow_html=True)
                fn = {"success": st.success, "warning": st.warning, "error": st.error}.get(tech_color, st.info)
                fn(action_badge(tech_grade))
            with ts2:
                st.markdown('<p class="sec-label">뉴스 상태</p>', unsafe_allow_html=True)
                if news_exit:
                    st.error(f"🚨 위험 — {row.get('News_Reason','')[:50]}")
                else:
                    st.success("✅ 이상 없음")
            with ts3:
                st.markdown('<p class="sec-label">AI 요약</p>', unsafe_allow_html=True)
                summary = generate_ai_summary(dict(row))
                if news_exit and tech_grade in ("HOLD_TIGHT", "HOLD"):
                    st.warning(f"⚠️ **REDUCE** — {summary}")
                elif tech_grade in ("HOLD_TIGHT", "HOLD") and not news_exit:
                    st.success(summary)
                else:
                    st.warning(summary)

            # ════ ROW 3: 좌(신호+모멘텀) / 우(손절+목표+포지션) ═
            left_col, right_col = st.columns([3, 2])

            with left_col:
                # ── 신호 칩 그리드 ──────────────────────
                st.markdown('<p class="sec-label">신호 체크</p>', unsafe_allow_html=True)
                signal_defs = [
                    ("손절 위",   "above_stop",      True),
                    ("VWAP",      "above_vwap",       True),
                    ("EMA21",     "above_ema21",      True),
                    ("Higher Low","higher_low",        True),
                    ("RS",        "rs_strong",         True),
                    ("RVOL",      "rvol_ok",           True),
                    ("매수압력",  "buying_pressure",   True),
                    ("섹터",      "sector_strong",     True),
                    ("카탈",      "catalyst_intact",   True),
                ]
                chips_html = ""
                for label, key, good in signal_defs:
                    ok = hd.get(key, good) == good
                    cls = "sig-ok" if ok else "sig-warn"
                    icon = "✓" if ok else "✗"
                    chips_html += f'<span class="sig-chip {cls}">{icon} {label}</span>'
                st.markdown(chips_html, unsafe_allow_html=True)

                # ── 모멘텀 수치 (한 줄) ─────────────────
                st.markdown('<p class="sec-label" style="margin-top:12px">모멘텀</p>', unsafe_allow_html=True)
                rvol    = row.get("RVOL", 0)
                rvol_3d = row.get("RVOL_3d", 0)
                rvol_5d = row.get("RVOL_5d", 0)
                rs      = row.get("RS_vs_Sector", 0)
                rvol_trend = "↑" if rvol >= rvol_3d >= rvol_5d else ("↓" if rvol <= rvol_5d else "→")
                rvol_color = "#81c784" if rvol >= 1.5 else ("#ef9a9a" if rvol < 1.0 else "#fff176")
                rs_color   = "#81c784" if rs > 0 else "#ef9a9a"
                etf = row.get("Sector_ETF", "QQQ")
                st.markdown(
                    f'<span style="color:{rvol_color};font-size:.9rem">RVOL {rvol:.1f}x {rvol_trend} '
                    f'<span style="color:#888">(3d:{rvol_3d:.1f} 5d:{rvol_5d:.1f})</span></span>'
                    f'&nbsp;&nbsp;&nbsp;'
                    f'<span style="color:{rs_color};font-size:.9rem">RS vs {etf} {rs:+.1f}% '
                    f'<span style="color:#888">({row.get("Ticker_Ret20d",0):+.1f}% vs {row.get("Sector_Ret20d",0):+.1f}%)</span></span>',
                    unsafe_allow_html=True
                )

                # ── Health Score 바 ──────────────────────
                st.markdown('<p class="sec-label" style="margin-top:12px">Health Score</p>', unsafe_allow_html=True)
                h_score = row["Health"]
                h_color = "#4caf50" if h_score >= 80 else ("#ff9800" if h_score >= 65 else "#f44336")
                score_items = [
                    ("손절위", hd.get("above_stop", False), 15),
                    ("VWAP",   hd.get("above_vwap", False), 12),
                    ("RS",     hd.get("rs_strong", False), 12),
                    ("HL",     hd.get("higher_low", False), 12),
                    ("EMA21",  hd.get("above_ema21", False), 8),
                    ("카탈",   hd.get("catalyst_intact", False), 10),
                    ("RVOL",   hd.get("rvol_ok", False), 8),
                    ("압력",   hd.get("buying_pressure", False), 8),
                ]
                earned_total = sum(pts for _, ok, pts in score_items if ok)
                breakdown = " · ".join(
                    f'<span style="color:{"#81c784" if ok else "#ef9a9a"}">{lbl} {pts if ok else 0}/{pts}</span>'
                    for lbl, ok, pts in score_items
                )
                st.markdown(
                    f'<span style="color:{h_color};font-size:1.1rem;font-weight:700">{h_score}/100 {row["Health_Grade"]}</span>'
                    f'<br><span style="font-size:.75rem">{breakdown}</span>',
                    unsafe_allow_html=True
                )

            with right_col:
                # ── 손절 ────────────────────────────────
                st.markdown('<p class="sec-label">손절</p>', unsafe_allow_html=True)
                stop_src = row.get("Suggested_Stop_Source", "-")
                st.markdown(
                    f'🟢 **활성** &nbsp; ${row.get("Stop",0):.2f} &nbsp;'
                    f'<span style="color:#888;font-size:.8rem">({stop_src})</span><br>'
                    f'🔴 **비상** &nbsp; ${row.get("Structural_Stop",0):.2f} &nbsp;'
                    f'<span style="color:#888;font-size:.8rem">(구조 붕괴선)</span><br>'
                    f'<span style="color:#666;font-size:.78rem">'
                    f'ATR ${row.get("ATR_Stop",0):.2f} &nbsp;|&nbsp; '
                    f'VWAP ${row.get("VWAP_Stop",0):.2f}</span>',
                    unsafe_allow_html=True
                )

                # ── 목표가 ──────────────────────────────
                st.markdown('<p class="sec-label" style="margin-top:10px">목표가</p>', unsafe_allow_html=True)
                st.markdown(
                    f'🎯 **보수적** &nbsp; ${row.get("Conservative_Target",0):.2f} &nbsp;'
                    f'<span style="color:#888;font-size:.8rem">(R:R {row.get("Suggested_RR",0):.1f})</span><br>'
                    f'<span style="color:#666;font-size:.78rem">'
                    f'R:R 2.5 ${row.get("RR_Target",0):.2f} &nbsp;|&nbsp; '
                    f'ATR ${row.get("ATR_Target",0):.2f} &nbsp;|&nbsp; '
                    f'저항 ${row.get("Resistance_Target",0):.2f}</span>',
                    unsafe_allow_html=True
                )

                # ── 포지션 ──────────────────────────────
                st.markdown('<p class="sec-label" style="margin-top:10px">포지션</p>', unsafe_allow_html=True)
                shares   = row.get("Shares", 0)
                pos_val  = row.get("Position_Value", 0)
                risk_usd = row.get("Risk_Dollars", 0)
                risk_pct = row.get("Risk_Pct_Account", 0)
                risk_color = "#ef9a9a" if risk_pct > 3 else "#81c784"
                st.markdown(
                    f'{shares}주 &nbsp; ${pos_val:,.0f} &nbsp;'
                    f'| Risk <span style="color:{risk_color};font-weight:600">'
                    f'${risk_usd:.2f} ({risk_pct:.1f}%)</span>',
                    unsafe_allow_html=True
                )

            # ════ ROW 4: 기술지표 바 (한 줄) ══════════════
            st.markdown('<p class="sec-label" style="margin-top:8px">기술지표 (5분봉)</p>', unsafe_allow_html=True)
            vwap_val  = row.get("VWAP", 0)
            vwap_dist = row.get("VWAP_Dist_Pct", 0)
            atr_val   = row.get("ATR_Val", 0)
            prev_low  = row.get("HL_Prev_Low")
            curr_low  = row.get("HL_Curr_Low")
            hl_ok     = row.get("HL_5m", False)
            hl_str    = (f"${prev_low:.2f}→${curr_low:.2f}" if prev_low and curr_low else "")
            hl_color  = "#81c784" if hl_ok else "#ef9a9a"
            vd_color  = "#fff176" if abs(vwap_dist) > 5 else "#81c784" if vwap_dist > 0 else "#ef9a9a"
            def ind_chip(label, ok):
                c = "#81c784" if ok else "#ef9a9a"
                return f'<span style="color:{c};font-size:.85rem;margin-right:12px">{"✅" if ok else "❌"} {label}</span>'
            st.markdown(
                f'<span style="color:#888;font-size:.85rem;margin-right:8px">VWAP</span>'
                f'<span style="color:{vd_color};font-size:.85rem;margin-right:4px">${vwap_val:.2f} ({vwap_dist:+.1f}%)</span>'
                f'&nbsp;&nbsp;'
                + ind_chip("EMA21", row.get("Above_EMA21", False))
                + ind_chip("EMA8",  row.get("Above_EMA8", False))
                + ind_chip("VWAP",  row.get("Above_VWAP", False))
                + f'<span style="color:{hl_color};font-size:.85rem;margin-right:12px">'
                  f'{"✅" if hl_ok else "❌"} Higher Low {hl_str}</span>'
                + f'<span style="color:#888;font-size:.85rem">ATR ${atr_val:.2f}</span>',
                unsafe_allow_html=True
            )


# ════════════════════════════════════════════════════════
#  TAB 3: JOURNAL
# ════════════════════════════════════════════════════════

def render_journal_tab():
    st.subheader("Journal — Past Results")

    output_dir = "output"
    if not os.path.exists(output_dir):
        st.info("No output files yet.")
        return

    all_files = sorted(os.listdir(output_dir), reverse=True)
    watchlists = [f for f in all_files if f.startswith("watchlist_")]
    monitors   = [f for f in all_files if f.startswith("monitor_")]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Screener Results**")
        if watchlists:
            sel = st.selectbox("Select", watchlists, key="j_watchlist")
            try:
                df = pd.read_csv(f"{output_dir}/{sel}")
                # Show only visible columns
                vis = [c for c in df.columns if not c.startswith("_")]
                st.dataframe(df[vis], use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(str(e))
        else:
            st.info("No screener results saved yet.")

    with col2:
        st.markdown("**Monitor Results**")
        if monitors:
            sel = st.selectbox("Select", monitors, key="j_monitor")
            try:
                df = pd.read_csv(f"{output_dir}/{sel}")
                st.dataframe(df, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(str(e))
        else:
            st.info("No monitor results saved yet.")


# ════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════

st.sidebar.title("Swing Screener")
st.sidebar.markdown("---")

tab1, tab2, tab3 = st.tabs(["Screener", "Position Monitor", "Journal"])

with tab1:
    render_screener_tab()

with tab2:
    render_monitor_tab()

with tab3:
    render_journal_tab()
