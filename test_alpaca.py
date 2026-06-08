"""
Alpaca API 단계별 테스트
Step 2: 연결 테스트
Step 3: AAPL 1분봉
Step 4: ALOY 최근 1분봉
"""
import os, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

API_KEY    = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# ── Step 2: 연결 테스트 ─────────────────────────────────────
print("=" * 50)
print("Step 2: API Connection Test")
print("=" * 50)

from alpaca.trading.client import TradingClient
client = TradingClient(api_key=API_KEY, secret_key=SECRET_KEY, paper=True)
acct = client.get_account()
print(f"Status       : {acct.status}")
print(f"Portfolio    : ${float(acct.portfolio_value):,.2f}")
print(f"Buying Power : ${float(acct.buying_power):,.2f}")
print()

# ── Step 3: AAPL 1분봉 ─────────────────────────────────────
print("=" * 50)
print("Step 3: AAPL 1min bars")
print("=" * 50)

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests   import StockBarsRequest
from alpaca.data.timeframe  import TimeFrame
from datetime import datetime, timedelta, timezone

data_client = StockHistoricalDataClient(api_key=API_KEY, secret_key=SECRET_KEY)

end   = datetime.now(timezone.utc)
start = end - timedelta(hours=2)

req = StockBarsRequest(
    symbol_or_symbols="AAPL",
    timeframe=TimeFrame.Minute,
    start=start,
    end=end,
    feed="iex",          # 무료 플랜: iex 사용
)
bars = data_client.get_stock_bars(req)
df_aapl = bars.df

if df_aapl.empty:
    print("No data (장 외 시간일 수 있음)")
else:
    # multi-index 처리
    if isinstance(df_aapl.index, type(df_aapl.index)) and df_aapl.index.nlevels > 1:
        df_aapl = df_aapl.xs("AAPL", level=0)
    print(f"Rows: {len(df_aapl)}")
    print(df_aapl[["open","high","low","close","volume"]].tail(5).to_string())
print()

# ── Step 4: ALOY 최근 1분봉 ────────────────────────────────
print("=" * 50)
print("Step 4: ALOY 1min bars")
print("=" * 50)

req2 = StockBarsRequest(
    symbol_or_symbols="ALOY",
    timeframe=TimeFrame.Minute,
    start=start,
    end=end,
    feed="iex",
)
bars2 = data_client.get_stock_bars(req2)
df_aloy = bars2.df

if df_aloy.empty:
    print("No data (장 외 시간 또는 ALOY 거래 없음)")
else:
    if df_aloy.index.nlevels > 1:
        df_aloy = df_aloy.xs("ALOY", level=0)
    print(f"Rows: {len(df_aloy)}")
    print(df_aloy[["open","high","low","close","volume"]].tail(5).to_string())
print()

print("All steps done.")
