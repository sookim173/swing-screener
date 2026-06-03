# Swing Screener — Day 1 MVP
**전략: 6-Module Framework (Market → Ignition → Quality → Supply → Chart → Risk)**

---

## 설치 (로컬)

```bash
pip install yfinance pandas numpy requests
```

## 실행

```bash
# Demo 모드 (mock data, API 불필요)
python screener_demo.py

# 실제 데이터 (yfinance, 인터넷 필요)
python screener.py
```

---

## 6-Module 구조

| 모듈 | 목적 | 배점 |
|---|---|---|
| Market Regime | 오늘 시장이 진입 가능한가? | 10 |
| Ignition | 지금 돈이 들어오는가? RVOL, PM Gap | 25 |
| Quality | 왜 오르는가? 실적, 뉴스 | 20 |
| Supply Structure | Float, Short Interest | 15 |
| Chart Structure | 패턴 (Pullback/Breakout/Gap Hold) | 20 |
| Risk / Trade Plan | R:R, 구조적 손절 | 10 |

**등급**: A(85+) → Trade Ready / B(75+) → Watchlist / C(65+) → 관찰 / D → 제외

---

## Trade Ready 조건 (전부 만족해야 YES)

```
Market Score >= 75
Total Score >= 75
RVOL >= 2.0
구조적 손절폭 <= 7%
R:R >= 1.8
```

---

## 티커 리스트 업데이트 방법

`screener.py` 하단의 `TEST_TICKERS` 리스트를 교체하면 됨.

추천: Finviz, TradingView 스크리너에서 당일 RVOL 높은 종목 30~50개 뽑아서 넣기.

---

## Day 2 업그레이드 예정

- Premarket Gap / Volume (real-time)
- Float, Short Interest (FMP or Polygon API)
- Sector ETF relative strength

## Day 3 업그레이드 예정

- 뉴스 품질 평가 (EPS Surprise %, 가이던스)
- VWAP hold / Gap hold 실시간 판단
- 구조적 손절 고도화

## Day 4

- Streamlit 대시보드
- Trade Journal

---

## API 키 설정 (실제 데이터 사용 시)

`config.py` 하단에 추가:

```python
# 실제 데이터 소스 (선택)
FMP_API_KEY = "your_key"       # financialmodelingprep.com (무료 티어 있음)
POLYGON_API_KEY = "your_key"   # polygon.io
FINNHUB_API_KEY = "your_key"   # finnhub.io
```

**추천 조합**: yfinance(가격) + FMP(실적/뉴스) + SEC API(무료, filing 위험 탐지)
