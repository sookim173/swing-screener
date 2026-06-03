# ============================================================
# Swing Screener - Config
# Strategy: Small-Cap Momentum Swing (6-Module Framework)
# ============================================================

ACCOUNT_SIZE = 1000
# RISK_PER_TRADE and TARGET_PCT are now managed in risk_plan.py (2% risk, 2.5R target)
MAX_STOP_PCT = 0.07       # structural stop > 7% → trade rejected (not capped)
MIN_RR = 1.8              # minimum reward/risk ratio

# Basic Filter
PRICE_MIN = 5
PRICE_MAX = 50
MARKET_CAP_MIN = 200_000_000
MARKET_CAP_MAX = 10_000_000_000
AVG_DOLLAR_VOLUME_MIN = 10_000_000   # $10M minimum, $20M preferred
AVG_VOLUME_MIN = 500_000
SPREAD_MAX = 0.005        # 0.5%

# Ignition Filter
RVOL_MIN = 2.0            # minimum to qualify
RVOL_STRONG = 3.0         # strong signal

# Supply Structure
FLOAT_MIN = 10_000_000    # 10M
FLOAT_MAX = 150_000_000   # 150M
SHORT_INTEREST_STRONG = 0.15  # 15%+ = squeeze potential

# Momentum (Universe Filter, not entry signal)
RETURN_5D_MIN = 0.03
RETURN_20D_MIN = 0.05

# Market Regime
MARKET_SCORE_MIN = 60     # below = no new entries
MARKET_SCORE_TRADE = 75   # 75+ = trade allowed

# Scoring Thresholds
SCORE_A = 85
SCORE_B = 75
SCORE_C = 65

# Sector ETFs to track
SECTOR_ETFS = {
    "Semiconductor": "SMH",
    "Software": "IGV",
    "Biotech": "XBI",
    "Financial": "XLF",
    "Energy": "XLE",
    "Industrial": "XLI",
    "Nuclear": "URA",
    "Cybersecurity": "CIBR",
    "Robotics": "BOTZ",
    "CleanEnergy": "ICLN",
}

MARKET_ETFS = ["QQQ", "SPY", "IWM", "^VIX"]
