"""
modules/catalyst.py
Catalyst quality scoring via Finnhub API (primary) + yfinance (fallback).

Finnhub endpoints used:
  - company_earnings()     : EPS actual vs estimate (last 4 quarters)
  - earnings_calendar()    : upcoming earnings date
  - company_news()         : recent news headlines (catalyst detection)

Evaluates:
  1. EPS surprise %
  2. Revenue surprise % (yfinance fallback)
  3. Post-earnings price reaction
  4. Recency (earnings within 30 days = PEAD active)
  5. News catalyst presence

Max score: 50 (normalized to 20pts in scoring.py)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import math
from datetime import datetime, timedelta


def score_catalyst(ticker: str, ind: dict) -> dict:
    details = {
        "catalyst_score":      0,
        "catalyst_grade":      "UNKNOWN",
        "eps_surprise_pct":    None,
        "rev_surprise_pct":    None,
        "earnings_days_ago":   None,
        "next_earnings_days":  None,
        "post_earnings_ret":   None,
        "news_catalyst":       False,
        "catalyst_reason":     "No data",
    }

    finnhub_ok = _try_finnhub(ticker, ind, details)
    if not finnhub_ok:
        _try_yfinance(ticker, ind, details)

    _apply_score(ind, details)
    return details


# ── Finnhub ──────────────────────────────────────────────────

def _try_finnhub(ticker: str, ind: dict, details: dict) -> bool:
    try:
        import finnhub
        api_key = os.getenv("FINNHUB_API_KEY", "")
        if not api_key:
            return False

        client = finnhub.Client(api_key=api_key)

        # 1. EPS surprise from earnings history
        earnings = client.company_earnings(ticker, limit=4)
        if earnings:
            latest = earnings[0]
            actual   = latest.get("actual")
            estimate = latest.get("estimate")
            period   = latest.get("period", "")  # "2025-03-31"

            if actual is not None and estimate is not None and not _isnan(estimate) and estimate != 0:
                surprise_pct = (actual - estimate) / abs(estimate) * 100
                details["eps_surprise_pct"] = round(surprise_pct, 1)

            if period:
                try:
                    earnings_date = datetime.strptime(period, "%Y-%m-%d")
                    days_ago = (datetime.now() - earnings_date).days
                    details["earnings_days_ago"] = days_ago
                except ValueError:
                    pass

        # 2. Next earnings date
        today = datetime.now()
        date_from = today.strftime("%Y-%m-%d")
        date_to   = (today + timedelta(days=60)).strftime("%Y-%m-%d")
        try:
            cal = client.earnings_calendar(
                _from=date_from, to=date_to, symbol=ticker, international=False
            )
            earnings_list = cal.get("earningsCalendar", [])
            if earnings_list:
                next_date_str = earnings_list[0].get("date", "")
                if next_date_str:
                    next_date = datetime.strptime(next_date_str, "%Y-%m-%d")
                    details["next_earnings_days"] = (next_date - today).days
        except Exception:
            pass

        # 3. Recent news catalyst (last 7 days)
        try:
            date_from_news = (today - timedelta(days=7)).strftime("%Y-%m-%d")
            news = client.company_news(ticker, _from=date_from_news, to=date_from)
            if news and len(news) >= 1:
                details["news_catalyst"] = True
        except Exception:
            pass

        # Return True only if we got at least earnings data
        return details["eps_surprise_pct"] is not None or details["earnings_days_ago"] is not None

    except Exception:
        return False


# ── yfinance fallback ─────────────────────────────────────────

def _try_yfinance(ticker: str, ind: dict, details: dict) -> None:
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)

        # earnings_history is more reliable than earnings_dates
        hist = t.earnings_history
        if hist is not None and not hist.empty:
            hist = hist.sort_index(ascending=False)
            latest = hist.iloc[0]
            eps_actual   = latest.get("epsActual")
            eps_estimate = latest.get("epsEstimate")

            if eps_actual is not None and eps_estimate is not None \
                    and not _isnan(eps_estimate) and eps_estimate != 0:
                surprise_pct = (eps_actual - eps_estimate) / abs(eps_estimate) * 100
                details["eps_surprise_pct"] = round(surprise_pct, 1)

            # Earnings date from index
            try:
                earnings_date = hist.index[0]
                if hasattr(earnings_date, "to_pydatetime"):
                    earnings_date = earnings_date.to_pydatetime()
                days_ago = (datetime.now() - earnings_date.replace(tzinfo=None)).days
                details["earnings_days_ago"] = days_ago
            except Exception:
                pass

        # Next earnings via calendar
        try:
            cal = t.calendar
            if cal is not None and not cal.empty:
                earning_date_col = [c for c in cal.columns if "Earnings" in str(c)]
                if earning_date_col:
                    val = cal[earning_date_col[0]].iloc[0]
                    if val:
                        next_date = datetime.strptime(str(val)[:10], "%Y-%m-%d")
                        details["next_earnings_days"] = (next_date - datetime.now()).days
        except Exception:
            pass

    except Exception:
        pass


# ── Scoring logic ─────────────────────────────────────────────

def _apply_score(ind: dict, details: dict) -> None:
    score   = 0
    reasons = []

    # 1. EPS Surprise
    sp = details.get("eps_surprise_pct")
    if sp is not None and not _isnan(sp):
        if sp >= 20:
            score += 20; reasons.append(f"EPS beat +{sp:.0f}% (strong)")
        elif sp >= 10:
            score += 15; reasons.append(f"EPS beat +{sp:.0f}%")
        elif sp >= 5:
            score += 10; reasons.append(f"EPS beat +{sp:.0f}% (light)")
        elif sp >= 0:
            score += 4;  reasons.append(f"EPS inline +{sp:.0f}%")
        else:
            score += 0;  reasons.append(f"EPS miss {sp:.0f}%")

    # 2. Recency (PEAD window)
    days_ago = details.get("earnings_days_ago")
    if days_ago is not None:
        if days_ago <= 7:
            score += 15; reasons.append(f"Earnings {days_ago}d ago (very fresh)")
        elif days_ago <= 14:
            score += 10; reasons.append(f"Earnings {days_ago}d ago (fresh)")
        elif days_ago <= 30:
            score += 5;  reasons.append(f"Earnings {days_ago}d ago")
        else:
            reasons.append(f"Earnings {days_ago}d ago (stale)")

    # 3. Post-earnings price reaction
    ret = ind.get("ret_5d", 0) if (days_ago or 999) <= 5 else ind.get("ret_20d", 0)
    details["post_earnings_ret"] = round(ret, 4)
    if ret >= 0.10:
        score += 15; reasons.append(f"Post-earnings +{ret:.1%} (strong hold)")
    elif ret >= 0.05:
        score += 10; reasons.append(f"Post-earnings +{ret:.1%}")
    elif ret >= 0:
        score += 5;  reasons.append(f"Post-earnings +{ret:.1%} (holding)")
    elif ret > -0.05:
        score += 3;  reasons.append(f"Post-earnings {ret:.1%} (absorbing)")

    # 4. News catalyst bonus
    if details.get("news_catalyst"):
        score += 5; reasons.append("Recent news catalyst")

    # 5. Upcoming earnings risk (penalize if < 3 days away)
    next_days = details.get("next_earnings_days")
    if next_days is not None and 0 <= next_days <= 3:
        score -= 10; reasons.append(f"Earnings in {next_days}d (binary risk)")

    score = max(0, min(score, 50))
    details["catalyst_score"]  = score
    details["catalyst_reason"] = " | ".join(reasons) if reasons else "No clear catalyst"

    if score >= 35:
        details["catalyst_grade"] = "STRONG"
    elif score >= 20:
        details["catalyst_grade"] = "MODERATE"
    elif score >= 10:
        details["catalyst_grade"] = "WEAK"
    else:
        details["catalyst_grade"] = "NONE"


def _isnan(val) -> bool:
    try:
        return math.isnan(float(val))
    except Exception:
        return True
