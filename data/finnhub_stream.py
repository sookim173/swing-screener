"""
data/finnhub_stream.py
Finnhub WebSocket — 장 중 실시간 RVOL 감시

사용법:
    from data.finnhub_stream import FinnhubStream

    stream = FinnhubStream(api_key="...", tickers=["MARA","HIMS","CELH"])
    stream.start()                   # 백그라운드 스레드로 시작

    # 주기적으로 현재 상태 조회
    snapshot = stream.get_snapshot("MARA")
    print(snapshot["intraday_rvol"])  # 예: 3.2

    stream.stop()

RVOL 계산 방식:
    intraday_rvol = 장 시작 이후 누적 거래량 / (avg_daily_vol × 경과시간비율)
    예) 10:30 기준 경과 = 60분 / 390분 = 15.4%
        avg_daily_vol = 2,000,000
        expected_vol  = 308,000
        actual_vol    = 600,000
        intraday_rvol = 1.95x
"""

import os
import json
import threading
import time
from datetime import datetime, timezone
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _et_offset() -> int:
    month = datetime.now().month
    return -4 if 3 <= month <= 11 else -5


class FinnhubStream:
    """
    Manages a Finnhub WebSocket connection for real-time trade data.
    Accumulates intraday volume per ticker and computes RVOL.
    WebSocket does NOT count toward Finnhub's 60 calls/min REST limit.
    Free plan: up to 50 tickers simultaneously.
    """

    WS_URL = "wss://ws.finnhub.io"
    MAX_TICKERS = 50

    def __init__(self, api_key: str = None, tickers: list = None,
                 avg_volumes: dict = None):
        """
        api_key     : Finnhub API key (reads FINNHUB_API_KEY env if None)
        tickers     : list of ticker symbols to watch (max 50)
        avg_volumes : dict {ticker: avg_daily_volume} for RVOL calculation
                      (if not provided, RVOL will be None)
        """
        self.api_key     = api_key or os.getenv("FINNHUB_API_KEY", "")
        self.tickers     = (tickers or [])[:self.MAX_TICKERS]
        self.avg_volumes = avg_volumes or {}

        # Per-ticker state
        self._volume:     dict = defaultdict(int)    # cumulative shares since open
        self._last_price: dict = {}
        self._trade_count: dict = defaultdict(int)
        self._lock        = threading.Lock()

        self._ws     = None
        self._thread = None
        self._running = False
        self._connected = False

    # ── Public API ───────────────────────────────────────

    def start(self):
        """Start WebSocket in a background thread."""
        if not self.api_key:
            print("  [FinnhubStream] No API key — stream disabled")
            return
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        # Wait briefly for connection
        for _ in range(20):
            if self._connected:
                break
            time.sleep(0.2)
        if self._connected:
            print(f"  [FinnhubStream] Connected — watching {len(self.tickers)} tickers")
        else:
            print("  [FinnhubStream] Connection timeout (market may be closed)")

    def stop(self):
        """Stop the WebSocket."""
        self._running = False
        if self._ws:
            self._ws.close()

    def update_tickers(self, tickers: list, avg_volumes: dict = None):
        """
        Swap the watched ticker list (max 50).
        Unsubscribes old tickers, subscribes new ones.
        """
        new_tickers = tickers[:self.MAX_TICKERS]
        if avg_volumes:
            self.avg_volumes.update(avg_volumes)

        if self._ws and self._connected:
            # Unsubscribe removed
            for t in set(self.tickers) - set(new_tickers):
                self._send({"type": "unsubscribe", "symbol": t})
            # Subscribe added
            for t in set(new_tickers) - set(self.tickers):
                self._send({"type": "subscribe", "symbol": t})

        with self._lock:
            self.tickers = new_tickers

    def reset_volumes(self):
        """Reset accumulated volume (call at 9:30 AM ET each day)."""
        with self._lock:
            self._volume.clear()
            self._trade_count.clear()

    def get_snapshot(self, ticker: str) -> dict:
        """
        Return current real-time snapshot for a ticker.
        {
            price          : float  — last trade price
            intraday_vol   : int    — shares traded since open
            intraday_rvol  : float  — volume / expected_volume (None if no avg)
            trade_count    : int    — number of trades seen
            day_fraction   : float  — elapsed portion of trading day
        }
        """
        et_off       = _et_offset()
        now_utc      = datetime.now(timezone.utc)
        open_utc     = now_utc.replace(hour=9 - et_off, minute=30,
                                       second=0, microsecond=0)
        elapsed_min  = max((now_utc - open_utc).total_seconds() / 60, 1)
        day_fraction = min(elapsed_min / 390, 1.0)

        with self._lock:
            vol   = self._volume.get(ticker, 0)
            price = self._last_price.get(ticker)
            count = self._trade_count.get(ticker, 0)

        # RVOL calculation
        intraday_rvol = None
        avg_vol = self.avg_volumes.get(ticker, 0)
        if avg_vol > 0 and day_fraction > 0:
            expected_vol  = avg_vol * day_fraction
            intraday_rvol = round(vol / expected_vol, 2) if expected_vol > 0 else None

        return {
            "ticker":        ticker,
            "price":         price,
            "intraday_vol":  vol,
            "intraday_rvol": intraday_rvol,
            "trade_count":   count,
            "day_fraction":  round(day_fraction, 3),
        }

    def get_all_snapshots(self) -> dict:
        """Return snapshots for all watched tickers, sorted by RVOL desc."""
        snaps = {t: self.get_snapshot(t) for t in self.tickers}
        return dict(sorted(
            snaps.items(),
            key=lambda x: x[1]["intraday_rvol"] or 0,
            reverse=True
        ))

    # ── Internal WebSocket logic ─────────────────────────

    def _run(self):
        import websocket as ws_lib

        url = f"{self.WS_URL}?token={self.api_key}"

        def on_open(ws):
            self._connected = True
            for ticker in self.tickers:
                self._send({"type": "subscribe", "symbol": ticker})

        def on_message(ws, message):
            try:
                data = json.loads(message)
                if data.get("type") != "trade":
                    return
                for trade in data.get("data", []):
                    symbol = trade.get("s")
                    price  = trade.get("p", 0)
                    volume = trade.get("v", 0)
                    if symbol:
                        with self._lock:
                            self._volume[symbol]      += int(volume)
                            self._last_price[symbol]   = float(price)
                            self._trade_count[symbol] += 1
            except Exception:
                pass

        def on_error(ws, error):
            print(f"  [FinnhubStream] Error: {error}")

        def on_close(ws, code, msg):
            self._connected = False
            if self._running:
                print("  [FinnhubStream] Disconnected — reconnecting in 5s...")
                time.sleep(5)
                self._run()   # reconnect

        self._ws = ws_lib.WebSocketApp(
            url,
            on_open    = on_open,
            on_message = on_message,
            on_error   = on_error,
            on_close   = on_close,
        )
        self._ws.run_forever(ping_interval=30, ping_timeout=10)

    def _send(self, payload: dict):
        if self._ws:
            try:
                self._ws.send(json.dumps(payload))
            except Exception:
                pass
