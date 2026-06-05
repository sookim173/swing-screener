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


POSITIONS_FILE  = "positions.json"
WATCHLIST_FILE  = "watchlist.json"


def load_watchlist() -> list:
    if not os.path.exists(WATCHLIST_FILE):
        return []
    try:
        with open(WATCHLIST_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_watchlist(items: list):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def add_to_watchlist(row: dict):
    """Screener 결과 row → watchlist.json에 추가. 중복 시 스킵."""
    items = load_watchlist()
    if any(it["ticker"] == row["Ticker"] for it in items):
        return False
    try:
        entry_v  = float(row.get("Entry") or 0)
        stop_v   = float(row.get("Stop")  or 0)
        target_v = float(row.get("Target") or 0)
    except (TypeError, ValueError):
        entry_v = stop_v = target_v = 0.0
    items.append({
        "ticker":     row["Ticker"],
        "added_date": date.today().isoformat(),
        "opp_score":  row.get("Opp_Score", row.get("Score", 0)),
        "pattern":    row.get("Pattern", ""),
        "catalyst":   row.get("Catalyst", ""),
        "price":      row.get("Price", 0),
        "entry":      entry_v,
        "stop":       stop_v,
        "target":     target_v,
        "rr":         row.get("R:R", 0),
        "rvol":       row.get("RVOL", 0),
        "float_m":    row.get("Float_M", 0),
        "pm_gap":     row.get("PM_Gap", "-"),
        "note":       "",
        "status":     "WATCH",
    })
    save_watchlist(items)
    return True


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

def render_market_score_detail(score: int | str, action: str, regime: dict):
    """Market Score 구성 요인을 한 눈에 볼 수 있는 설명 패널."""

    ACTION_COLOR = {
        "AGGRESSIVE":      ("#1b5e20", "🟢", "공격적 진입 가능 — 시장이 강세. 좋은 셋업은 풀 사이즈로."),
        "SELECTIVE":       ("#1565c0", "🔵", "선별적 진입 — 시장 양호하나 완벽한 셋업만 집중."),
        "WATCHLIST_ONLY":  ("#e65100", "🟡", "관찰만 — 신규 진입 자제. 기존 포지션만 관리."),
        "NO_NEW_ENTRIES":  ("#b71c1c", "🔴", "신규 진입 금지 — 시장 약세. 현금 보유 우선."),
    }
    bg, dot, action_desc = ACTION_COLOR.get(action, ("#333", "⚪", action))

    with st.expander(f"{dot} **Market Score {score}/100 — {action}** (클릭하여 상세 보기)", expanded=False):
        st.markdown(
            f'<div style="background:{bg}22;border-left:4px solid {bg};padding:8px 14px;'
            f'border-radius:4px;margin-bottom:12px">'
            f'<span style="color:#fff;font-size:.9rem">{action_desc}</span></div>',
            unsafe_allow_html=True
        )

        # 점수 구성 테이블
        rows = []

        # QQQ
        qqq_above = regime.get("qqq_above_ma20")
        qqq_5d    = regime.get("qqq_5d", 0)
        if qqq_above is not None:
            if qqq_above:
                rows.append(("QQQ", "+30pt", "QQQ 종가 > 20일 MA",
                              f"나스닥 추세 살아있음. 성장주 환경 우호적."))
            else:
                rows.append(("QQQ", "+0pt", "QQQ 종가 < 20일 MA",
                              f"나스닥 추세 훼손. 성장주 환경 악화."))

            if qqq_5d > 0.01:
                rows.append(("QQQ 5D", "+15pt", f"QQQ 5일 수익률 {qqq_5d:+.1%} (> +1%)",
                              "단기 모멘텀 강함. 매수세 유입 중."))
            elif qqq_5d > -0.01:
                rows.append(("QQQ 5D", "+5pt", f"QQQ 5일 수익률 {qqq_5d:+.1%} (−1%~+1%)",
                              "단기 횡보. 방향성 불분명."))
            else:
                rows.append(("QQQ 5D", "+0pt", f"QQQ 5일 수익률 {qqq_5d:+.1%} (< −1%)",
                              "단기 하락 압력. 신규 진입 주의."))

        # SPY
        spy_above = regime.get("spy_above_ma20")
        if spy_above is not None:
            if spy_above:
                rows.append(("SPY", "+20pt", "SPY 종가 > 20일 MA",
                              "S&P500 추세 유지. 시장 전반 건강."))
            else:
                rows.append(("SPY", "+0pt", "SPY 종가 < 20일 MA",
                              "S&P500 추세 이탈. 광범위한 약세."))

        # IWM
        iwm_above = regime.get("iwm_above_ma20")
        if iwm_above is not None:
            if iwm_above:
                rows.append(("IWM", "+20pt", "IWM(소형주) 종가 > 20일 MA",
                              "소형주 강세 = 위험 선호 환경. 스윙에 유리."))
            else:
                rows.append(("IWM", "+0pt", "IWM(소형주) 종가 < 20일 MA",
                              "소형주 약세 = 안전 자산 선호. 스윙 리스크 증가."))

        # VIX
        vix_level  = regime.get("vix_level")
        vix_5d_chg = regime.get("vix_5d_change", 0)
        if vix_level is not None:
            if vix_level < 20:
                vix_pt = "+15pt"
                vix_note = "공포 낮음. 시장 안정적."
            elif vix_level < 25:
                vix_pt = "+8pt"
                vix_note = "약간 불안. 변동성 주의."
            elif vix_level > 30:
                vix_pt = "−15pt"
                vix_note = "공포 구간. 급락 리스크 높음."
            else:
                vix_pt = "+0pt"
                vix_note = "중립 구간."
            rows.append(("VIX", vix_pt, f"VIX {vix_level:.1f}", vix_note))

            if vix_5d_chg > 0.20:
                rows.append(("VIX 급등", "−10pt", f"VIX 5일 변화 {vix_5d_chg:+.0%} (> +20%)",
                              "공포 급격히 증가. 매도 압력 확대 중."))

        # 테이블 렌더링
        for etf, pts, condition, meaning in rows:
            color = "#4caf50" if pts.startswith("+") and pts != "+0pt" else \
                    ("#f44336" if pts.startswith("−") else "#888")
            st.markdown(
                f'<div style="display:flex;align-items:baseline;gap:10px;margin:4px 0">'
                f'<span style="min-width:60px;font-weight:700;color:#aaa;font-size:.8rem">{etf}</span>'
                f'<span style="min-width:52px;font-weight:700;color:{color};font-size:.9rem">{pts}</span>'
                f'<span style="color:#ddd;font-size:.85rem">{condition}</span>'
                f'<span style="color:#888;font-size:.8rem;margin-left:6px">— {meaning}</span>'
                f'</div>',
                unsafe_allow_html=True
            )

        # 최대 점수 안내
        st.markdown(
            '<div style="margin-top:10px;color:#666;font-size:.78rem">'
            '최대 가능 점수: QQQ MA(30) + QQQ 5D(15) + SPY(20) + IWM(20) + VIX(15) = 100pt</div>',
            unsafe_allow_html=True
        )


def render_ticker_detail(ticker: str, df: pd.DataFrame):
    """Screener 후보 티커의 상세 리포트: 차트 + 지표 설명 + 뉴스."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from data.price_loader import get_price_data

    row = df[df["Ticker"] == ticker].iloc[0] if not df.empty and ticker in df["Ticker"].values else None

    st.markdown(f"## 📊 {ticker} 상세 리포트")

    # ── 차트 ─────────────────────────────────────────────
    with st.spinner(f"{ticker} 차트 로드 중..."):
        price_df = get_price_data(ticker, days=60)

    if price_df is not None and not price_df.empty:
        # 이동평균 계산
        price_df["ema8"]  = price_df["close"].ewm(span=8,  adjust=False).mean()
        price_df["ema21"] = price_df["close"].ewm(span=21, adjust=False).mean()
        price_df["ema50"] = price_df["close"].ewm(span=50, adjust=False).mean()
        avg_vol = price_df["volume"].rolling(20).mean()

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            row_heights=[0.7, 0.3],
            vertical_spacing=0.03,
        )

        # 캔들스틱
        fig.add_trace(go.Candlestick(
            x=price_df.index,
            open=price_df["open"], high=price_df["high"],
            low=price_df["low"],  close=price_df["close"],
            name=ticker,
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ), row=1, col=1)

        # EMA lines
        fig.add_trace(go.Scatter(x=price_df.index, y=price_df["ema8"],
                                  line=dict(color="#ff9800", width=1.2), name="EMA 8"), row=1, col=1)
        fig.add_trace(go.Scatter(x=price_df.index, y=price_df["ema21"],
                                  line=dict(color="#42a5f5", width=1.2), name="EMA 21"), row=1, col=1)
        fig.add_trace(go.Scatter(x=price_df.index, y=price_df["ema50"],
                                  line=dict(color="#ab47bc", width=1.2, dash="dot"), name="EMA 50"), row=1, col=1)

        # Entry / Stop / Target 라인 (row 데이터가 있으면)
        if row is not None:
            entry  = row.get("Entry")
            stop   = row.get("Stop")
            target = row.get("Target")
            x0, x1 = price_df.index[0], price_df.index[-1]
            if entry:
                fig.add_hline(y=float(entry), line=dict(color="#42a5f5", dash="dash", width=1.5),
                              annotation_text=f"Entry ${entry}", row=1, col=1)
            if stop:
                fig.add_hline(y=float(stop), line=dict(color="#ef5350", dash="dash", width=1.5),
                              annotation_text=f"Stop ${stop}", row=1, col=1)
            if target:
                fig.add_hline(y=float(target), line=dict(color="#26a69a", dash="dash", width=1.5),
                              annotation_text=f"Target ${target}", row=1, col=1)

        # 거래량 바
        colors = ["#26a69a" if c >= o else "#ef5350"
                  for c, o in zip(price_df["close"], price_df["open"])]
        fig.add_trace(go.Bar(x=price_df.index, y=price_df["volume"],
                             marker_color=colors, name="Volume", opacity=0.7), row=2, col=1)
        fig.add_trace(go.Scatter(x=price_df.index, y=avg_vol,
                                  line=dict(color="#ffca28", width=1), name="Vol MA20"), row=2, col=1)

        fig.update_layout(
            height=520,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            margin=dict(l=10, r=10, t=30, b=10),
            legend=dict(orientation="h", y=1.02, x=0),
        )
        fig.update_yaxes(title_text="Price", row=1, col=1)
        fig.update_yaxes(title_text="Volume", row=2, col=1)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("차트 데이터를 불러올 수 없습니다.")

    # ── 지표 설명 ─────────────────────────────────────────
    if row is not None:
        st.markdown("### 📋 지표 해설")
        tabs_m = st.tabs(["핵심 지표", "리스크 플랜", "스코어 분석"])

        # 공통 값 추출
        try:
            entry_v   = float(row.get("Entry") or 0)
            stop_v    = float(row.get("Stop") or 0)
            atr_stop_v = float(row.get("ATR_Stop") or 0)
            target_v  = float(row.get("Target") or 0)
            atr_v     = float(row.get("ATR") or 0)
            price_v   = float(row.get("Price") or 0)
            rr_v      = float(row.get("R:R") or 0)
            risk_v    = entry_v - stop_v if entry_v and stop_v else 0
            stop_pct  = risk_v / entry_v * 100 if entry_v else 0
            reward_v  = target_v - entry_v if target_v and entry_v else 0
            rvol      = float(row.get("RVOL") or 0)
            rvol_3d   = float(row.get("RVOL_3D") or 0)
            float_m   = float(row.get("Float_M") or 0)
            score_v   = float(row.get("Score") or 0)
        except Exception:
            entry_v = stop_v = atr_stop_v = target_v = atr_v = price_v = 0
            rr_v = risk_v = stop_pct = reward_v = rvol = rvol_3d = float_m = score_v = 0

        def card(title: str, value: str, explanation: str, good: bool | None = None):
            if good is True:
                border = "#2e7d32"
            elif good is False:
                border = "#c62828"
            else:
                border = "#444"
            st.markdown(
                f"""<div style="border-left:3px solid {border};padding:8px 12px;margin-bottom:10px;background:#1e1e1e;border-radius:4px">
                <span style="font-size:.8rem;color:#aaa;text-transform:uppercase;letter-spacing:.05em">{title}</span><br>
                <span style="font-size:1.1rem;font-weight:700;color:#fff">{value}</span><br>
                <span style="font-size:.82rem;color:#ccc">{explanation}</span>
                </div>""",
                unsafe_allow_html=True
            )

        with tabs_m[0]:
            cols = st.columns(2)

            # Score
            grade = row.get("Grade", "-")
            above_75 = score_v >= 75
            if score_v >= 85:
                score_judge = f"85점 이상 → 고품질 셋업. 6개 모듈 대부분이 강한 신호."
            elif score_v >= 75:
                score_judge = f"75~85점 → 진입 검토 가능. 일부 모듈 약점 있으나 전반적으로 유효."
            else:
                score_judge = f"75점 미만 → 아직 진입 부적합. 약한 모듈 확인 필요."
            with cols[0]:
                card("종합 점수 (Score)", f"{score_v:.1f} / 100",
                     f"시장·점화·품질·공급·차트·리스크 6개 모듈 합산. {score_judge}", good=above_75)

            # Grade
            grade_map = {"A": ("85점 이상", True), "B": ("75~85점", True),
                         "C": ("65~75점", None), "D": ("65점 미만", False)}
            g_desc, g_good = grade_map.get(str(grade)[0], ("-", None))
            with cols[1]:
                card("등급 (Grade)", str(grade),
                     f"{g_desc} 구간. A/B = 진입 검토, C = 관망, D = 제외.", good=g_good)

            # Pattern
            pattern = row.get("Pattern", "-")
            pattern_desc = {
                "Bull Flag":           "강한 상승 후 짧은 깃발형 눌림. 이전 상승 에너지 재충전 중.",
                "Momentum Pullback":   "상승 추세 중 단기 눌림목. EMA 지지 후 재상승 노리는 구조.",
                "Cup Base":            "컵 형태 베이스 완성. 오른쪽 립 돌파 시 진입.",
                "High Tight Flag":     "폭발적 상승 후 타이트한 통합. 매우 희귀하고 강력한 패턴.",
                "VCP":                 "변동성 수축 패턴. 진폭이 줄어들며 에너지 압축 중.",
                "Flat Base":           "평평한 횡보 베이스. 일정 박스권에서 공급 소진 확인.",
                "No Pattern":          "명확한 패턴 미감지. 진입 시점 불분명.",
            }
            p_desc = pattern_desc.get(pattern, "감지된 기술적 패턴 구조.")
            with cols[0]:
                card("차트 패턴 (Pattern)", pattern, p_desc,
                     good=(pattern != "No Pattern"))

            # RVOL
            if rvol >= 2.0:
                rvol_judge = f"20일 평균의 {rvol:.1f}배 → 강한 점화 신호. 기관/세력 참여 가능성."
            elif rvol >= 1.5:
                rvol_judge = f"20일 평균의 {rvol:.1f}배 → 평균 이상 관심. 모멘텀 형성 중."
            elif rvol >= 1.0:
                rvol_judge = f"20일 평균의 {rvol:.1f}배 → 평균 수준. 돌파 확인엔 부족."
            else:
                rvol_judge = f"20일 평균의 {rvol:.1f}배 → 거래 부진. 관심 부족."
            with cols[1]:
                card("상대 거래량 (RVOL)", f"{rvol:.1f}x",
                     f"오늘 거래량 ÷ 20일 평균 거래량. {rvol_judge}", good=(rvol >= 1.5))

            # RVOL_3D
            rvol_trend = "증가 추세" if rvol >= rvol_3d else "감소 추세"
            with cols[0]:
                card("RVOL 3일 평균", f"{rvol_3d:.1f}x" if rvol_3d else "-",
                     f"최근 3일 RVOL 평균. 오늘 RVOL({rvol:.1f}x)과 비교하면 거래량 {rvol_trend}.",
                     good=(rvol >= rvol_3d))

            # 5D%
            ret5 = row.get("5D%", "-")
            try:
                ret5_f = float(str(ret5).replace("%","").replace("+",""))
                ret5_good = ret5_f > 3
                ret5_note = f"{ret5_f:+.1f}% → " + ("강한 단기 모멘텀." if ret5_f > 5 else
                             "보통 수준." if ret5_f > 0 else "단기 약세. 눌림 깊이 확인 필요.")
            except Exception:
                ret5_good, ret5_note = None, ""
            with cols[1]:
                card("5일 수익률 (5D%)", str(ret5),
                     f"최근 5거래일 가격 변화. {ret5_note}", good=ret5_good)

            # RS_QQQ
            rs_qqq = row.get("RS_QQQ", "-")
            try:
                rs_f = float(str(rs_qqq).replace("%","").replace("+",""))
                rs_good = rs_f > 0
                rs_note = (f"나스닥보다 {rs_f:+.1f}%p 강함. " + ("섹터·시장을 리드하는 강세주." if rs_f > 5 else "소폭 아웃퍼폼.")) if rs_f > 0 else f"나스닥보다 {rs_f:.1f}%p 약함. 상대적 약세."
            except Exception:
                rs_good, rs_note = None, ""
            with cols[0]:
                card("QQQ 대비 RS", str(rs_qqq),
                     f"20일 수익률 - QQQ 20일 수익률. {rs_note}", good=rs_good)

            # Float_M
            if float_m < 10:
                float_note = f"{float_m:.1f}M주 유통. 소형 Float → 작은 매수세에도 주가 급등 가능."
                float_good = True
            elif float_m < 50:
                float_note = f"{float_m:.1f}M주 유통. 중형 Float → 적절한 유동성."
                float_good = True
            else:
                float_note = f"{float_m:.1f}M주 유통. 대형 Float → 큰 매수세 필요. 폭발력 제한."
                float_good = False
            with cols[1]:
                card("유통주식수 (Float)", f"{float_m:.1f}M주",
                     float_note, good=float_good)

            # Short%
            short_str = row.get("Short%", "-")
            try:
                short_f = float(str(short_str).replace("%",""))
                if short_f >= 20:
                    short_note = f"유통주 {short_f:.0f}%가 공매도. 상승 시 숏 커버 강제 → 추가 상승 가속 가능."
                    short_good = True
                elif short_f >= 10:
                    short_note = f"유통주 {short_f:.0f}%가 공매도. 보통 수준."
                    short_good = None
                else:
                    short_note = f"유통주 {short_f:.0f}%만 공매도. 숏 스퀴즈 기대 낮음."
                    short_good = None
            except Exception:
                short_note, short_good = "", None
            with cols[0]:
                card("공매도 비율 (Short%)", str(short_str), short_note, good=short_good)

            # PM_Gap
            pm_gap = row.get("PM_Gap", "-")
            try:
                pm_f = float(str(pm_gap).replace("%","").replace("+",""))
                if pm_f >= 3:
                    pm_note = f"프리마켓에서 전일比 +{pm_f:.1f}% 갭업. 강한 수급 신호. 카탈리스트 확인 필요."
                    pm_good = True
                elif pm_f > 0:
                    pm_note = f"프리마켓 +{pm_f:.1f}% 소폭 강세."
                    pm_good = None
                else:
                    pm_note = f"프리마켓 {pm_f:.1f}%. 수급 약함."
                    pm_good = False
            except Exception:
                pm_note, pm_good = "프리마켓 데이터 없음.", None
            with cols[1]:
                card("프리마켓 갭 (PM_Gap)", str(pm_gap), pm_note, good=pm_good)

            # Catalyst
            cat = row.get("Catalyst", "-")
            cat_desc = {"A": "강한 펀더멘털 촉매 존재 (실적 서프라이즈·FDA 승인·계약 등). 상승 지속 가능성 높음.",
                        "B": "보통 수준의 촉매. 뉴스는 있으나 임팩트 불확실.",
                        "C": "약한 촉매 또는 섹터 테마 수혜 수준.",
                        "D": "뚜렷한 촉매 없음. 순수 기술적 셋업으로만 접근."}
            with cols[0]:
                card("카탈리스트 등급", str(cat),
                     cat_desc.get(str(cat)[0], "카탈리스트 강도 등급."),
                     good=(str(cat)[0] in ("A", "B")))

            # Next_Earn
            ne = row.get("Next_Earn", "-")
            try:
                ne_days = int(str(ne).replace("d",""))
                if ne_days <= 7:
                    ne_note = f"실적 발표 {ne_days}일 후. 이번 주 진입 시 실적 리스크 노출. 사이즈 축소 또는 진입 대기 권장."
                    ne_good = False
                elif ne_days <= 21:
                    ne_note = f"실적 발표 {ne_days}일 후. 진입 후 실적 전 익절 전략 검토."
                    ne_good = None
                else:
                    ne_note = f"실적 발표 {ne_days}일 후. 스윙 기간 내 실적 리스크 낮음."
                    ne_good = True
            except Exception:
                ne_note, ne_good = "실적 일정 미확인.", None
            with cols[1]:
                card("다음 실적 발표", str(ne), ne_note, good=ne_good)

        with tabs_m[1]:
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("진입가 (Entry)",  f"${entry_v:.2f}")
            r2.metric("손절가 (Stop)",   f"${stop_v:.2f}")
            r3.metric("ATR 손절",        f"${atr_stop_v:.2f}" if atr_stop_v else "-")
            r4.metric("목표가 (Target)", f"${target_v:.2f}")

            rr_color = "normal" if rr_v >= 1.8 else "inverse"
            c1, c2, c3 = st.columns(3)
            c1.metric("R:R", f"{rr_v:.2f}", delta="기준 충족" if rr_v >= 1.8 else "1.8 미달",
                      delta_color=rr_color)
            c2.metric("손절 폭", f"{stop_pct:.1f}%", delta="적정" if stop_pct <= 7 else "7% 초과",
                      delta_color="normal" if stop_pct <= 7 else "inverse")
            c3.metric("진입 준비", row.get("Ready", "-"))

            st.markdown("---")
            cols2 = st.columns(2)

            # Entry 설명
            entry_from_price = (entry_v - price_v) / price_v * 100 if price_v else 0
            with cols2[0]:
                card("진입가 $" + f"{entry_v:.2f}", "",
                     f"현재가 ${price_v:.2f}에서 {entry_from_price:+.1f}% 위. "
                     f"패턴 돌파 레벨로 설정됨. 이 가격을 상향 돌파해야 매수 트리거 발동.")

            # Stop 설명
            with cols2[1]:
                card("손절가 $" + f"{stop_v:.2f}", "",
                     f"진입가 ${entry_v:.2f}에서 ${risk_v:.2f}({stop_pct:.1f}%) 아래. "
                     f"최근 스윙 로우 또는 패턴 저점 기준. 이 아래 종가 발생 시 스윙 구조 붕괴 → 즉시 손절.",
                     good=(stop_pct <= 7))

            # ATR Stop 설명
            with cols2[0]:
                atr_stop_pct = (entry_v - atr_stop_v) / entry_v * 100 if entry_v and atr_stop_v else 0
                card("ATR 손절 $" + f"{atr_stop_v:.2f}", "",
                     f"진입가 - ATR({atr_v:.2f}) × 1.5 = ${atr_stop_v:.2f}. "
                     f"구조적 손절({stop_v:.2f})보다 {'더 타이트' if atr_stop_v > stop_v else '더 여유 있는'} 레벨. "
                     f"둘 중 유리한 쪽 선택.")

            # Target 설명
            with cols2[1]:
                card("목표가 $" + f"{target_v:.2f}", "",
                     f"진입가 ${entry_v:.2f} + 리스크({risk_v:.2f}) × {rr_v:.1f} = ${target_v:.2f}. "
                     f"상승 여력 +{reward_v/entry_v*100:.1f}% ({reward_v:.2f}달러). "
                     f"주요 저항선 또는 R:R 목표 중 보수적 값 사용.",
                     good=True)

            # ATR 설명
            with cols2[0]:
                card("ATR(14) " + f"${atr_v:.2f}", "",
                     f"14일 평균 일변동 폭 ${atr_v:.2f}. 하루에 이 정도 움직이는 종목. "
                     f"손절 계산에 사용 (Stop = Entry - 1.5×ATR). "
                     f"ATR이 클수록 = 변동성 높음 = 포지션 사이즈 줄여야.")

            # R:R 설명
            with cols2[1]:
                card("R:R " + f"{rr_v:.2f}", "",
                     f"수익 가능 폭(${reward_v:.2f}) ÷ 손절 폭(${risk_v:.2f}) = {rr_v:.2f}. "
                     f"1달러 잃는 리스크로 {rr_v:.2f}달러 벌 수 있는 구조. "
                     f"{'✅ 1.8 이상으로 진입 기준 충족.' if rr_v >= 1.8 else '⚠ 1.8 미달. 진입 기준 미충족.'}",
                     good=(rr_v >= 1.8))

        with tabs_m[2]:
            bk_labels = ["Market", "Ignition", "Quality", "Supply", "Chart", "Risk"]
            bk_cols   = ["_Mkt", "_Ign", "_Qual", "_Sup", "_Chart", "_Risk"]
            bk_vals   = [row.get(c, 0) for c in bk_cols]
            bk_df = pd.DataFrame({"Module": bk_labels, "Score": bk_vals})
            st.bar_chart(bk_df.set_index("Module"))

            mkt_score = row.get("_market_score", 0)
            bk_dynamic = {
                "Market":   f"{bk_vals[0]:.0f}pt — 시장 레짐 점수 {mkt_score}/100 반영. "
                            + ("시장 강세 구간. 셋업 유효." if bk_vals[0] >= 15 else
                               "시장 중립. 셋업 품질이 더 중요." if bk_vals[0] >= 10 else
                               "시장 약세. 좋은 셋업도 실패 확률 높음."),
                "Ignition": f"{bk_vals[1]:.0f}pt — 점화 신호 강도. RVOL {rvol:.1f}x, PM갭 {row.get('PM_Gap','-')}. "
                            + ("강한 점화 — 기관 참여 신호." if bk_vals[1] >= 18 else
                               "보통 수준." if bk_vals[1] >= 12 else "점화 약함. 매수세 부족."),
                "Quality":  f"{bk_vals[2]:.0f}pt — RS vs QQQ {row.get('RS_QQQ','-')}, 5D {row.get('5D%','-')}. "
                            + ("강한 모멘텀 종목." if bk_vals[2] >= 14 else "보통." if bk_vals[2] >= 9 else "모멘텀 약함."),
                "Supply":   f"{bk_vals[3]:.0f}pt — Float {float_m:.0f}M주, Short {row.get('Short%','-')}. "
                            + ("공급 타이트 → 폭발력 높음." if bk_vals[3] >= 12 else "보통." if bk_vals[3] >= 8 else "공급 과다."),
                "Chart":    f"{bk_vals[4]:.0f}pt — 패턴: {row.get('Pattern','-')}. "
                            + ("패턴 완성도 높음." if bk_vals[4] >= 15 else "패턴 불완전." if bk_vals[4] >= 8 else "패턴 미감지."),
                "Risk":     f"{bk_vals[5]:.0f}pt — R:R {rr_v:.2f}, 손절 {stop_pct:.1f}%. "
                            + ("리스크 관리 우수." if bk_vals[5] >= 12 else "보통." if bk_vals[5] >= 8 else "리스크 불량."),
            }
            for lbl, score in zip(bk_labels, bk_vals):
                color = "#4caf50" if score >= 15 else ("#ff9800" if score >= 10 else "#f44336")
                st.markdown(
                    f'<span style="color:{color};font-weight:700;font-size:.95rem">{lbl}</span>'
                    f' — <span style="color:#ccc;font-size:.85rem">{bk_dynamic[lbl]}</span>',
                    unsafe_allow_html=True
                )
                st.markdown("")

    # ── 뉴스 ─────────────────────────────────────────────
    st.markdown("### 📰 최근 뉴스")
    news = _get_news(ticker)
    if not news:
        st.info("뉴스를 불러올 수 없습니다. (FINNHUB_API_KEY 확인)")
    else:
        from modules.position_manager.exit_rules import NEGATIVE_KEYWORDS
        for item in news[:10]:
            headline = item.get("headline", "")
            summary  = item.get("summary", "")
            url      = item.get("url", "")
            source   = item.get("source", "")
            dt_ts    = item.get("datetime", 0)
            try:
                dt_str = datetime.fromtimestamp(dt_ts).strftime("%Y-%m-%d %H:%M") if dt_ts else ""
            except Exception:
                dt_str = ""
            text_lower = (headline + summary).lower()
            is_negative = any(kw in text_lower for kw in NEGATIVE_KEYWORDS)
            badge = "🚨" if is_negative else "📄"
            with st.expander(f"{badge} {headline}  —  {source}  {dt_str}"):
                if summary:
                    st.write(summary)
                if url:
                    st.markdown(f"[원문 보기]({url})")


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
            "Opp_Score":    final["opp_score"],
            "Entry_Hint":   final["entry_hint"],
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
    return df_r, df_n, market_score, action, regime


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
                df_r, df_n, mkt, act, regime = run_screener_cached(tickers)
            st.session_state.update({"sc_results": df_r, "sc_nearmiss": df_n,
                                     "sc_market": mkt, "sc_action": act,
                                     "sc_regime": regime})
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

    df     = st.session_state["sc_results"]
    nm     = st.session_state.get("sc_nearmiss", pd.DataFrame())
    mkt    = st.session_state.get("sc_market", "-")
    act    = st.session_state.get("sc_action", "-")
    regime = st.session_state.get("sc_regime", {})

    # Metric bar
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Market Score", f"{mkt}/100")
    c2.metric("Regime", act)
    ready_n = len(df[df["Ready"] == "✅ YES"]) if not df.empty and "Ready" in df.columns else 0
    c3.metric("Trade Ready", ready_n)
    c4.metric("Watch List", len(df) - ready_n if not df.empty else 0)

    # Market Score 상세 설명
    if regime:
        render_market_score_detail(mkt, act, regime)

    st.markdown("---")

    if df.empty:
        st.info("No candidates passed all filters today.")
        return

    st.subheader("Candidates")
    display_cols = ["", "Ticker", "Grade", "Opp_Score", "Entry_Hint", "Pattern", "Price",
                    "RVOL", "RVOL_3D", "5D%", "RS_QQQ", "Float_M", "Short%",
                    "PM_Gap", "Catalyst", "Next_Earn", "ATR",
                    "Entry", "Stop", "ATR_Stop", "Target", "R:R", "Ready"]
    display_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(
        df[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Opp_Score":  st.column_config.ProgressColumn(
                "Opp Score", min_value=0, max_value=100, format="%.1f",
                help="Phase 1: Market+Ignition+Catalyst+Supply (EOD기반, /100)"),
            "Entry_Hint": st.column_config.NumberColumn(
                "Entry Hint", format="%.1f",
                help="Chart+Risk 힌트 (EOD proxy). Phase 2에서 Intraday 기반으로 교체 예정"),
            "R:R":   st.column_config.NumberColumn("R:R", format="%.2f"),
            "ATR":   st.column_config.NumberColumn("ATR", format="%.2f"),
        }
    )

    # ── Watchlist 추가 ────────────────────────────────────
    st.markdown("#### ★ Watchlist에 추가")
    st.caption("Phase 2 진입 분석 대상으로 저장합니다. Watchlist 탭에서 확인·관리하세요.")
    ticker_options_wl = df["Ticker"].tolist() if not df.empty else []
    already_wl = [it["ticker"] for it in load_watchlist()]
    available  = [t for t in ticker_options_wl if t not in already_wl]
    if available:
        selected_wl = st.multiselect(
            "종목 선택 (복수 가능)",
            options=available,
            key="wl_add_multi",
        )
        if st.button("Watchlist에 추가", key="wl_add_btn", type="primary"):
            added = []
            for t in selected_wl:
                row_data = df[df["Ticker"] == t].iloc[0].to_dict()
                if add_to_watchlist(row_data):
                    added.append(t)
            if added:
                st.success(f"추가됨: {', '.join(added)}")
            else:
                st.info("선택한 종목이 이미 Watchlist에 있습니다.")
    else:
        st.info("모든 후보가 이미 Watchlist에 있습니다.")

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

    # ── Ticker Detail Report ─────────────────────────────
    st.markdown("---")
    st.subheader("Ticker Detail Report")
    ticker_options = df["Ticker"].tolist() if not df.empty else []
    selected_ticker = st.selectbox(
        "종목 선택 (클릭하면 상세 리포트)",
        ["— 선택하세요 —"] + ticker_options,
        key="detail_ticker"
    )
    if selected_ticker != "— 선택하세요 —":
        render_ticker_detail(selected_ticker, df)

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

            # ════ ROW 2: 판정 3분할 ═══════════════════════
            tech_grade = row.get("Technical_Grade", "HOLD")
            news_exit  = row.get("News_Exit", False)
            tech_color = {"HOLD_TIGHT": "success", "HOLD": "success",
                          "CAUTION": "warning", "WEAK_EXIT": "error"}.get(tech_grade, "info")
            summary    = generate_ai_summary(dict(row))

            ts1, ts2, ts3 = st.columns([1, 1, 2])
            with ts1:
                st.caption("차트 상태")
                fn = {"success": st.success, "warning": st.warning,
                      "error": st.error}.get(tech_color, st.info)
                fn(action_badge(tech_grade))
            with ts2:
                st.caption("뉴스 상태")
                if news_exit:
                    st.error(f"🚨 {row.get('News_Reason','')[:45]}")
                else:
                    st.success("✅ 이상 없음")
            with ts3:
                st.caption("AI 요약")
                if news_exit and tech_grade in ("HOLD_TIGHT", "HOLD"):
                    st.warning(f"⚠️ **REDUCE** — {summary}")
                elif tech_grade in ("HOLD_TIGHT", "HOLD") and not news_exit:
                    st.success(summary)
                else:
                    st.warning(summary)
            if row["Stop_Moved"]:
                st.success(f"📈 Stop raised — {row['Stop_Reason']}")

            st.markdown("---")

            # ════ ROW 3: 균등 4열 ════════════════════════
            rvol    = row.get("RVOL", 0)
            rvol_3d = row.get("RVOL_3d", 0)
            rvol_5d = row.get("RVOL_5d", 0)
            rs      = row.get("RS_vs_Sector", 0)
            etf     = row.get("Sector_ETF", "QQQ")
            shares  = row.get("Shares", 0)
            pos_val = row.get("Position_Value", 0)
            risk_usd = row.get("Risk_Dollars", 0)
            risk_pct = row.get("Risk_Pct_Account", 0)
            stop_src = row.get("Suggested_Stop_Source", "-")
            rvol_trend = "↑" if rvol >= rvol_3d >= rvol_5d else ("↓" if rvol <= rvol_5d else "→")

            col_a, col_b, col_c, col_d = st.columns(4)

            # ── A열: 신호 체크 + Health ──────────────────
            with col_a:
                st.caption("신호 체크")
                signal_defs = [
                    ("손절 위",    "above_stop",       True),
                    ("VWAP",       "above_vwap",        True),
                    ("EMA21",      "above_ema21",       True),
                    ("Higher Low", "higher_low",         True),
                    ("RS",         "rs_strong",          True),
                    ("RVOL",       "rvol_ok",            True),
                    ("매수압력",   "buying_pressure",    True),
                    ("섹터",       "sector_strong",      True),
                    ("카탈",       "catalyst_intact",    True),
                ]
                chips = ""
                for label, key, good in signal_defs:
                    ok  = hd.get(key, good) == good
                    cls = "sig-ok" if ok else "sig-warn"
                    chips += f'<span class="sig-chip {cls}">{"✓" if ok else "✗"} {label}</span>'
                st.markdown(chips, unsafe_allow_html=True)

                st.markdown("")
                h = row["Health"]
                h_color = "#4caf50" if h >= 80 else ("#ff9800" if h >= 65 else "#f44336")
                score_items = [
                    ("손절",  hd.get("above_stop",False),15), ("VWAP", hd.get("above_vwap",False),12),
                    ("RS",    hd.get("rs_strong",False),12),  ("HL",   hd.get("higher_low",False),12),
                    ("EMA21", hd.get("above_ema21",False),8), ("카탈", hd.get("catalyst_intact",False),10),
                    ("RVOL",  hd.get("rvol_ok",False),8),     ("압력", hd.get("buying_pressure",False),8),
                ]
                bd = "  ".join(
                    f'{"✅" if ok else "❌"}{lbl} {pts if ok else 0}/{pts}'
                    for lbl, ok, pts in score_items
                )
                st.markdown(
                    f'<span style="color:{h_color};font-weight:700;font-size:1rem">'
                    f'Health {h}/100 · {row["Health_Grade"]}</span>'
                    f'<br><span style="color:#888;font-size:.72rem">{bd}</span>',
                    unsafe_allow_html=True
                )

            # ── B열: 손절 ────────────────────────────────
            with col_b:
                st.caption("손절")
                st.metric("🟢 활성 손절", f"${row.get('Stop',0):.2f}",
                          delta=stop_src, delta_color="off",
                          help="현재 실제 적용 중인 손절선")
                st.metric("🔴 비상 손절", f"${row.get('Structural_Stop',0):.2f}",
                          delta="구조 붕괴선", delta_color="off",
                          help="이탈 시 스윙 트렌드 붕괴")
                st.caption(
                    f"ATR ${row.get('ATR_Stop',0):.2f}  |  "
                    f"VWAP ${row.get('VWAP_Stop',0):.2f}"
                )

            # ── C열: 목표가 ──────────────────────────────
            with col_c:
                st.caption("목표가")
                st.metric("🎯 보수적 목표", f"${row.get('Conservative_Target',0):.2f}",
                          delta=f"남은 R:R {row.get('Suggested_RR',0):.1f}",
                          delta_color="normal")
                st.metric("R:R 2.5 목표", f"${row.get('RR_Target',0):.2f}",
                          help="entry + risk × 2.5 (진입 시 확정)")
                st.caption(
                    f"ATR ${row.get('ATR_Target',0):.2f}  |  "
                    f"저항 ${row.get('Resistance_Target',0):.2f}"
                )

            # ── D열: 포지션 + 모멘텀 ─────────────────────
            with col_d:
                st.caption("포지션 / 리스크")
                st.metric("포지션", f"{shares}주  ·  ${pos_val:,.0f}")
                st.metric("리스크", f"${risk_usd:.2f}  ({risk_pct:.1f}%)",
                          delta="⚠ 과다" if risk_pct > 3 else "적정",
                          delta_color="inverse" if risk_pct > 3 else "normal")

                st.markdown("")
                st.caption("모멘텀")
                rvol_c = "🟢" if rvol >= 1.5 else ("🔴" if rvol < 1.0 else "🟡")
                rs_c   = "🟢" if rs > 0 else "🔴"
                st.markdown(
                    f"{rvol_c} RVOL **{rvol:.1f}x** {rvol_trend}  "
                    f"*(3d {rvol_3d:.1f} / 5d {rvol_5d:.1f})*  \n"
                    f"{rs_c} RS vs {etf} **{rs:+.1f}%**  "
                    f"*({row.get('Ticker_Ret20d',0):+.1f}% vs {row.get('Sector_Ret20d',0):+.1f}%)*"
                )

            # ════ ROW 4: 기술지표 6열 ════════════════════
            st.markdown("---")
            vwap_val  = row.get("VWAP", 0)
            vwap_dist = row.get("VWAP_Dist_Pct", 0)
            atr_val   = row.get("ATR_Val", 0)
            prev_low  = row.get("HL_Prev_Low")
            curr_low  = row.get("HL_Curr_Low")
            hl_ok     = row.get("HL_5m", False)
            hl_label  = ("✅ 유지" if hl_ok else "❌ 붕괴") + (
                         f"  {prev_low:.2f}→{curr_low:.2f}" if prev_low and curr_low else "")
            tc1, tc2, tc3, tc4, tc5, tc6 = st.columns(6)
            tc1.metric("VWAP", f"${vwap_val:.2f}",
                       delta=f"{vwap_dist:+.1f}%",
                       delta_color="off" if abs(vwap_dist) > 5 else "normal")
            tc2.metric("Above VWAP",  "✅" if row.get("Above_VWAP")  else "❌")
            tc3.metric("Above EMA21", "✅" if row.get("Above_EMA21") else "❌",
                       help=f"EMA21 ${row.get('EMA21_Val',0):.2f}" if row.get('EMA21_Val') else None)
            tc4.metric("Above EMA8",  "✅" if row.get("Above_EMA8")  else "❌")
            tc5.metric("Higher Low",  hl_label)
            tc6.metric("ATR(14)", f"${atr_val:.2f}" if atr_val else "-")


# ════════════════════════════════════════════════════════
#  TAB 3: WATCHLIST  (Phase 1 → Phase 2 브릿지)
# ════════════════════════════════════════════════════════

_STATUS_OPTS   = ["WATCH", "SETTING_UP", "BUYABLE", "FAILED", "PROMOTED"]
_STATUS_COLOR  = {
    "WATCH":       ("#1565c0", "👀"),
    "SETTING_UP":  ("#f57f17", "🔄"),
    "BUYABLE":     ("#1b5e20", "✅"),
    "FAILED":      ("#b71c1c", "❌"),
    "PROMOTED":    ("#4a148c", "📌"),
}


def _status_badge(status: str) -> str:
    dot, icon = _STATUS_COLOR.get(status, ("#888", "⚪"))[0], _STATUS_COLOR.get(status, ("#888", "⚪"))[1]
    return f"{icon} {status}"


def _get_news_age(ticker: str) -> dict:
    """가장 최근 뉴스의 경과 시간(시간 단위) + freshness 등급 반환."""
    news = _get_news(ticker)
    if not news:
        return {"age_h": None, "freshness": "-", "headline": ""}
    # datetime 기준 최신 뉴스 선택
    latest = max(news, key=lambda n: n.get("datetime", 0))
    dt_ts  = latest.get("datetime", 0)
    if not dt_ts:
        return {"age_h": None, "freshness": "-", "headline": ""}
    age_h = (datetime.now().timestamp() - dt_ts) / 3600
    if   age_h <= 4:   freshness = "★★★★★"
    elif age_h <= 12:  freshness = "★★★★☆"
    elif age_h <= 24:  freshness = "★★★☆☆"
    elif age_h <= 48:  freshness = "★★☆☆☆"
    else:              freshness = "★☆☆☆☆"
    return {
        "age_h":    round(age_h, 1),
        "freshness": freshness,
        "headline":  latest.get("headline", "")[:80],
    }


def _run_entry_analysis(items: list) -> dict:
    """
    Watchlist 전체 종목 Entry Validation 실행.
    transition_entry를 item["transitions"]에 기록하고 watchlist 저장.
    {ticker: result} 반환.
    """
    from modules.position_manager.intraday_data import get_intraday_df
    from modules.entry_validator import validate_entry
    from data.price_loader import get_ticker_info

    results = {}
    prog    = st.progress(0, text="Entry Analysis 실행 중...")
    total   = len(items)

    for i, item in enumerate(items):
        ticker = item["ticker"]
        prog.progress((i + 1) / total, text=f"Analyzing {ticker}...")

        df_5m = get_intraday_df(ticker, "5m")
        if df_5m is None or df_5m.empty:
            result = {
                "entry_score": 0, "engine_status": "WATCH",
                "reason": "Intraday 데이터 없음 (장 외 시간 또는 API 오류)",
                "failed_reasons": [], "signals": {}, "score_breakdown": {},
                "transition_entry": None,
                "news_age": {"age_h": None, "freshness": "-", "headline": ""},
            }
        else:
            info      = get_ticker_info(ticker)
            avg_vol   = info.get("avg_volume", 0) or 1
            result    = validate_entry(df_5m, avg_vol, item.get("opp_score", 0))
            result["news_age"] = _get_news_age(ticker)

        # Transition 기록: 직전 마지막 기록과 status가 다르거나 처음이면 추가
        te = result.get("transition_entry")
        if te:
            transitions = item.setdefault("transitions", [])
            if not transitions or transitions[-1]["status"] != te["status"]:
                transitions.append(te)
            # 최대 20개 유지
            item["transitions"] = transitions[-20:]

        results[ticker] = result

    prog.empty()
    save_watchlist(items)   # transition 기록 영구 저장
    return results


def _entry_status_color(status: str) -> str:
    return {
        "BUYABLE":    "#1b5e20",
        "SETTING_UP": "#f57f17",
        "WEAKENING":  "#e65100",
        "FAILED":     "#b71c1c",
        "WATCH":      "#1565c0",
    }.get(status, "#444")


def _close_vs_high_grade(close_pos: float) -> tuple[str, str]:
    """종가 위치 → 등급 레이블 + 색상."""
    if   close_pos >= 0.80: return "VERY STRONG 🟢", "#1b5e20"
    elif close_pos >= 0.60: return "STRONG 🟢",       "#2e7d32"
    elif close_pos >= 0.40: return "NEUTRAL 🟡",      "#f57f17"
    elif close_pos >= 0.20: return "WEAK 🔴",          "#c62828"
    else:                   return "VERY WEAK 🔴",     "#b71c1c"


def _render_entry_panel(ticker: str, result: dict, opp_score: float,
                        transitions: list | None = None):
    """Entry Analysis 결과 패널 렌더링."""
    import plotly.graph_objects as go

    es      = result.get("entry_score", 0)
    status  = result.get("engine_status", "WATCH")
    reason  = result.get("reason", "-")
    sigs    = result.get("signals", {})
    bk      = result.get("score_breakdown", {})
    color   = _entry_status_color(status)
    na      = result.get("news_age", {})

    # ── 상태 배너 ──────────────────────────────────────────
    st.markdown(
        f'<div style="background:{color}33;border-left:4px solid {color};'
        f'padding:8px 14px;border-radius:4px;margin-bottom:10px">'
        f'<span style="color:#fff;font-weight:700;font-size:1rem">'
        f'Engine: {status}  |  Entry Score {es:.1f}/100</span><br>'
        f'<span style="color:#ddd;font-size:.85rem">{reason}</span></div>',
        unsafe_allow_html=True
    )

    if not sigs:
        return

    # ── 핵심 신호 메트릭 Row 1 ────────────────────────────
    price     = sigs.get("price", 0)
    vwap      = sigs.get("vwap", 0)
    vwap_dist = sigs.get("vwap_distance_pct", 0)
    vol_pace  = sigs.get("volume_pace", 0)
    day_high  = sigs.get("day_high", 0)
    cp        = sigs.get("close_position", 0)
    cp_label, cp_color = _close_vs_high_grade(cp)
    age_h     = na.get("age_h")
    freshness = na.get("freshness", "-")

    e1, e2, e3, e4, e5, e6 = st.columns(6)
    e1.metric("현재가",      f"${price:.2f}")
    e2.metric("VWAP",        f"${vwap:.2f}",
              delta=f"{vwap_dist:+.1f}%",
              delta_color="normal" if vwap_dist >= 0 else "inverse")
    e3.metric("Volume Pace", f"{vol_pace:.1f}x",
              delta="강함" if vol_pace >= 3 else ("보통" if vol_pace >= 1.5 else "약함"),
              delta_color="normal" if vol_pace >= 2 else "inverse")
    e4.metric("Day High",    f"${day_high:.2f}",
              delta=f"고점比 {sigs.get('from_high_pct',0):.1f}%",
              delta_color="inverse" if sigs.get("from_high_pct", 0) < -10 else "off")

    # Close vs High — 큼직하게 색상 등급 표시
    e5.markdown(
        f'<div style="padding:4px 0">'
        f'<span style="font-size:.75rem;color:#aaa">Close vs High</span><br>'
        f'<span style="font-size:1.5rem;font-weight:800;color:{cp_color}">'
        f'{cp*100:.0f}%</span><br>'
        f'<span style="font-size:.8rem;color:{cp_color}">{cp_label}</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    # News Age
    if age_h is not None:
        age_str  = f"{age_h:.0f}h" if age_h >= 1 else f"{age_h*60:.0f}m"
        age_color = "#4caf50" if age_h <= 4 else ("#ff9800" if age_h <= 24 else "#f44336")
        e6.markdown(
            f'<div style="padding:4px 0">'
            f'<span style="font-size:.75rem;color:#aaa">News Age</span><br>'
            f'<span style="font-size:1.5rem;font-weight:800;color:{age_color}">'
            f'{age_str}</span><br>'
            f'<span style="font-size:.8rem;color:#888">{freshness}</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        if na.get("headline"):
            st.caption(f"📰 {na['headline']}")
    else:
        e6.metric("News Age", "-")

    # ── ORB + 구조 신호 Row 2 ─────────────────────────────
    orb15h = sigs.get("orb_15_high", 0)
    orb15l = sigs.get("orb_15_low",  0)
    o1, o2, o3, o4, o5 = st.columns(5)
    o1.metric("ORB 15분 High", f"${orb15h:.2f}",
              delta="돌파" if sigs.get("above_orb_15_high") else "미달",
              delta_color="normal" if sigs.get("above_orb_15_high") else "off")
    o2.metric("ORB 15분 Low",  f"${orb15l:.2f}",
              delta="유지" if not sigs.get("orb_15_low_broken") else "이탈",
              delta_color="normal" if not sigs.get("orb_15_low_broken") else "inverse")
    o3.metric("VWAP 위 / 아래",
              f"{sigs.get('bars_above_vwap',0)} / {sigs.get('bars_below_vwap',0)}봉",
              delta="VWAP Reclaim" if sigs.get("vwap_reclaim") else "",
              delta_color="normal")
    o4.metric("Higher Low",
              f"{sigs.get('higher_low_count',0)}회",
              delta_color="off")
    o5.metric("Lower High",
              f"{sigs.get('lower_high_count',0)}회",
              delta="Fakeout" if sigs.get("fakeout") else "",
              delta_color="inverse" if sigs.get("fakeout") else "off")

    # ── 점수 구성 차트 ────────────────────────────────────
    if bk:
        score_labels = ["VWAP(25)", "ORB(25)", "Volume(20)", "Structure(20)", "Position(10)"]
        score_vals   = [bk.get("vwap",0), bk.get("orb",0), bk.get("volume",0),
                        bk.get("structure",0), bk.get("position",0)]
        max_vals     = [25, 25, 20, 20, 10]
        bar_colors   = ["#4caf50" if v >= m * 0.7 else ("#ff9800" if v >= m * 0.4 else "#f44336")
                        for v, m in zip(score_vals, max_vals)]
        fig = go.Figure(go.Bar(
            x=score_labels, y=score_vals,
            marker_color=bar_colors, text=score_vals, textposition="auto",
        ))
        fig.update_layout(
            height=180, template="plotly_dark",
            margin=dict(l=0, r=0, t=10, b=10),
            yaxis=dict(range=[0, 25]),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── 실패 이유 ─────────────────────────────────────────
    fail_reasons = result.get("failed_reasons", [])
    if fail_reasons:
        st.error("실패 조건: " + " | ".join(fail_reasons))

    # ── State Transition History ──────────────────────────
    if transitions:
        st.markdown("**📋 State Transition History**")
        timeline_html = '<div style="font-size:.82rem;line-height:1.9">'
        status_dot = {
            "BUYABLE":    "🟢", "SETTING_UP": "🟡", "WEAKENING": "🟠",
            "FAILED":     "🔴", "WATCH":      "🔵",
        }
        for t in transitions:
            dot   = status_dot.get(t["status"], "⚪")
            score = t.get("entry_score", 0)
            timeline_html += (
                f'<span style="color:#888">{t["time"]}</span>  '
                f'{dot} <b>{t["status"]}</b>  '
                f'<span style="color:#aaa">Entry {score:.0f}</span>  '
                f'<span style="color:#666">— {t.get("reason","")[:60]}</span><br>'
            )
        timeline_html += "</div>"
        st.markdown(timeline_html, unsafe_allow_html=True)


def render_watchlist_tab():
    st.subheader("Watchlist — Phase 2 진입 검토")
    st.caption(
        "Screener에서 선택한 후보들의 진입 타이밍을 분석합니다. "
        "**Run Entry Analysis** 로 Intraday 신호를 확인하고 Status를 관리하세요."
    )

    items = load_watchlist()
    if not items:
        st.info("Watchlist가 비어 있습니다. Screener 탭에서 종목을 추가하세요.")
        return

    # ── Entry Analysis 실행 버튼 ─────────────────────────
    col_run, col_info = st.columns([1, 3])
    with col_run:
        run_entry = st.button("▶ Run Entry Analysis", type="primary",
                              use_container_width=True,
                              help="5분봉 데이터로 VWAP/ORB/Volume Pace/구조 분석 (장중 실행 권장)")
    with col_info:
        st.caption(
            "yfinance 5분봉 기준 (15분 지연). "
            "VWAP · ORB 15분 · Volume Pace · Higher Low / Lower High 구조 분석."
        )

    if run_entry:
        with st.spinner("Intraday 데이터 분석 중..."):
            entry_results = _run_entry_analysis(items)
        st.session_state["entry_results"] = entry_results
        st.success(f"{len(entry_results)}개 종목 분석 완료")

    entry_results = st.session_state.get("entry_results", {})

    # ── 요약 메트릭 ──────────────────────────────────────
    # 분석 결과 반영 시 engine_status, 아니면 저장된 status 사용
    def effective_status(item):
        er = entry_results.get(item["ticker"])
        return er["engine_status"] if er else item.get("status", "WATCH")

    total      = len(items)
    buyable    = sum(1 for it in items if effective_status(it) == "BUYABLE")
    setting_up = sum(1 for it in items if effective_status(it) == "SETTING_UP")
    weakening  = sum(1 for it in items if effective_status(it) == "WEAKENING")
    watch      = sum(1 for it in items if effective_status(it) == "WATCH")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("전체",        total)
    m2.metric("BUYABLE",     buyable,    delta="진입 가능" if buyable else None,
              delta_color="normal" if buyable else "off")
    m3.metric("SETTING UP",  setting_up)
    m4.metric("WEAKENING",   weakening,  delta_color="inverse" if weakening else "off")
    m5.metric("WATCH",       watch)

    st.markdown("---")

    # ── 종목 카드 ─────────────────────────────────────────
    updated        = False
    remove_tickers = []

    for idx, item in enumerate(items):
        ticker  = item["ticker"]
        status  = item.get("status", "WATCH")
        er      = entry_results.get(ticker)
        es      = er["entry_score"] if er else None
        eng_st  = er["engine_status"] if er else None
        opp_sc  = item.get("opp_score", 0)
        pattern = item.get("pattern", "-")
        added   = item.get("added_date", "")

        # 헤더에 두 점수 모두 표시
        dot     = _STATUS_COLOR.get(status, ("#888", "⚪"))[1]
        score_str = f"Opp {opp_sc:.1f}"
        if es is not None:
            score_str += f"  ·  Entry {es:.1f}"
        if eng_st and eng_st != status:
            score_str += f"  →  Engine: **{eng_st}**"

        with st.expander(
            f"{dot} **{ticker}**  |  {score_str}  |  {pattern}  |  {status}  |  {added}",
            expanded=(status in ("BUYABLE", "SETTING_UP") or
                      (eng_st in ("BUYABLE", "SETTING_UP")))
        ):
            # ── Entry Analysis 결과 (분석 실행 후) ────────
            if er:
                _render_entry_panel(ticker, er, opp_score=opp_sc,
                                    transitions=item.get("transitions"))
                st.markdown("---")

            col_l, col_r = st.columns([2, 1])

            with col_l:
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Price",   f"${item.get('price', 0):.2f}")
                c2.metric("Entry",   f"${item.get('entry', 0):.2f}" if item.get('entry') else "-")
                c3.metric("Stop",    f"${item.get('stop',  0):.2f}" if item.get('stop')  else "-")
                c4.metric("Target",  f"${item.get('target',0):.2f}" if item.get('target') else "-")
                c5.metric("R:R",     f"{item.get('rr', 0):.2f}"    if item.get('rr')     else "-")

                d1, d2, d3 = st.columns(3)
                d1.metric("Opp Score", f"{opp_sc:.1f}")
                d2.metric("RVOL",      f"{item.get('rvol', 0):.1f}x")
                d3.metric("Float",     f"{item.get('float_m', 0):.1f}M")

                new_note = st.text_area(
                    "메모",
                    value=item.get("note", ""),
                    height=60,
                    key=f"note_{ticker}_{idx}",
                    placeholder="진입 조건, 관찰 포인트 등 자유롭게 기록",
                )
                if new_note != item.get("note", ""):
                    item["note"] = new_note
                    updated = True

            with col_r:
                # Engine 추천 Status 적용 버튼
                if eng_st and eng_st != status:
                    st.caption(f"Engine 추천: **{eng_st}**")
                    if st.button(f"→ {eng_st} 적용", key=f"apply_eng_{ticker}_{idx}",
                                 use_container_width=True):
                        item["status"] = eng_st
                        updated = True
                        st.rerun()

                new_status = st.selectbox(
                    "수동 Status",
                    options=_STATUS_OPTS,
                    index=_STATUS_OPTS.index(status) if status in _STATUS_OPTS else 0,
                    key=f"status_{ticker}_{idx}",
                )
                if new_status != status:
                    item["status"] = new_status
                    updated = True

                st.markdown("")

                if st.button("📌 Monitor로 승격", key=f"promote_{ticker}_{idx}",
                             use_container_width=True):
                    positions = load_positions()
                    if ticker not in [p["ticker"] for p in positions]:
                        entry_v = item.get("entry") or item.get("price") or 0
                        stop_v  = item.get("stop")  or 0
                        risk    = round(float(entry_v) - float(stop_v), 2) if entry_v and stop_v else float(entry_v) * 0.05
                        positions.append({
                            "ticker":          ticker,
                            "entry_date":      date.today().isoformat(),
                            "entry_price":     float(entry_v),
                            "shares":          0,
                            "structural_stop": float(stop_v),
                            "current_stop":    float(stop_v),
                            "initial_target":  float(item.get("target") or 0),
                            "risk_per_share":  max(risk, 0.01),
                            "pattern":         item.get("pattern", ""),
                            "catalyst":        item.get("catalyst", ""),
                            "sector_etf":      "QQQ",
                            "qqq_ret_at_entry": 0.0,
                        })
                        save_positions(positions)
                        item["status"] = "PROMOTED"
                        updated = True
                        st.success(f"{ticker} → Monitor에 추가됨")
                    else:
                        st.info(f"{ticker}은 이미 Monitor에 있습니다.")

                if st.button("🗑 제거", key=f"remove_{ticker}_{idx}",
                             use_container_width=True):
                    remove_tickers.append(ticker)

    if remove_tickers:
        items = [it for it in items if it["ticker"] not in remove_tickers]
        updated = True

    if updated:
        save_watchlist(items)
        st.rerun()

    # ── 전체 목록 테이블 ──────────────────────────────────
    st.markdown("---")
    st.markdown("#### 전체 목록")
    summary_rows = []
    for it in items:
        er    = entry_results.get(it["ticker"])
        es    = er["entry_score"] if er else None
        eng   = er["engine_status"] if er else "-"
        summary_rows.append({
            "Status":       _status_badge(it.get("status", "WATCH")),
            "Ticker":       it["ticker"],
            "Opp Score":    it.get("opp_score", 0),
            "Entry Score":  es if es is not None else "-",
            "Engine":       eng,
            "Pattern":      it.get("pattern", "-"),
            "Catalyst":     it.get("catalyst", "-"),
            "Price":        it.get("price", 0),
            "Entry":        it.get("entry", 0),
            "R:R":          it.get("rr", 0),
            "Added":        it.get("added_date", ""),
            "Note":         it.get("note", "")[:40],
        })
    if summary_rows:
        st.dataframe(
            pd.DataFrame(summary_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Opp Score": st.column_config.ProgressColumn(
                    "Opp Score", min_value=0, max_value=100, format="%.1f"),
                "Entry Score": st.column_config.ProgressColumn(
                    "Entry Score", min_value=0, max_value=100, format="%.1f"),
            }
        )


# ════════════════════════════════════════════════════════
#  TAB 4: JOURNAL
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

tab1, tab2, tab3, tab4 = st.tabs(["Screener", "Watchlist", "Position Monitor", "Journal"])

with tab1:
    render_screener_tab()

with tab2:
    render_watchlist_tab()

with tab3:
    render_monitor_tab()

with tab4:
    render_journal_tab()
