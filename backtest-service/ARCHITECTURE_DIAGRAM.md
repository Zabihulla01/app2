# Two-Stage Architecture: Visual Flow

## System Overview

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                    Two-Stage Analysis System                   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

    API Request                           API Response
    /analyze/BTC-USD                      Decision + Details
         │                                      ▲
         │                                      │
         ▼                                      │
┌─────────────────────┐                        │
│   Fetch OHLCV Data  │                        │
│   - CoinGecko       │                        │
│   - yfinance        │                        │
└──────────┬──────────┘                        │
           │                                    │
           ▼                                    │
┌─────────────────────┐                        │
│  Add Indicators     │                        │
│  - RSI, MACD, EMA   │                        │
│  - ADX, ATR, BB     │                        │
└──────────┬──────────┘                        │
           │                                    │
           ▼                                    │
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
┃              STAGE 1: ANALYSIS            ┃  │
┃         (stage1_analysis.py)              ┃  │
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫  │
┃                                           ┃  │
┃  ✓ Trend Analysis                         ┃  │
┃    - Direction (BULLISH/BEARISH/NEUTRAL)  ┃  │
┃    - Strength (0-100)                     ┃  │
┃    - Structure (UPTREND/DOWNTREND/RANGE)  ┃  │
┃                                           ┃  │
┃  ✓ Support & Resistance                   ┃  │
┃    - Key levels                           ┃  │
┃    - Strength scores                      ┃  │
┃                                           ┃  │
┃  ✓ Volume Analysis                        ┃  │
┃    - Volume trend                         ┃  │
┃    - Spike detection                      ┃  │
┃                                           ┃  │
┃  ✓ Technical Indicators                   ┃  │
┃    - RSI (signal, divergence)             ┃  │
┃    - MACD (trend, crossover)              ┃  │
┃    - EMA (alignment, golden/death cross)  ┃  │
┃    - ATR (volatility state)               ┃  │
┃    - Bollinger (squeeze, position)        ┃  │
┃    - ADX (trend strength)                 ┃  │
┃                                           ┃  │
┃  ✓ Market Health                          ┃  │
┃    - Overall score                        ┃  │
┃    - Trend quality                        ┃  │
┃    - Momentum quality                     ┃  │
┃                                           ┃  │
┃  ✓ Multi-Timeframe Confirmation           ┃  │
┃  ✓ Liquidity Analysis                     ┃  │
┃  ✓ Volatility Regime                      ┃  │
┃  ✓ AI Summary (bias, factors, warnings)   ┃  │
┃  ✓ Confidence & Risk Scores               ┃  │
┃                                           ┃  │
┗━━━━━━━━━━━━━━━━┬━━━━━━━━━━━━━━━━━━━━━━━━┛  │
                 │                             │
                 │  Store Results              │
                 ▼                             │
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
┃         ANALYSIS CACHE                    ┃  │
┃       (analysis_cache.py)                 ┃  │
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫  │
┃                                           ┃  │
┃  {                                        ┃  │
┃    symbol: "BTC-USD"                      ┃  │
┃    timeframe: "1h"                        ┃  │
┃    timestamp: "2024-01-01T12:00:00Z"      ┃  │
┃    current_price: 40000                   ┃  │
┃    atr: 500                               ┃  │
┃    trend: "BULLISH"                       ┃  │
┃    trend_strength: 85                     ┃  │
┃    rsi_analysis: {...}                    ┃  │
┃    macd_analysis: {...}                   ┃  │
┃    ema_analysis: {...}                    ┃  │
┃    market_health: {...}                   ┃  │
┃    confidence_score: 75                   ┃  │
┃    risk_score: 80                         ┃  │
┃    ai_summary: {...}                      ┃  │
┃    ... 30+ metrics ...                    ┃  │
┃  }                                        ┃  │
┃                                           ┃  │
┗━━━━━━━━━━━━━━━━┬━━━━━━━━━━━━━━━━━━━━━━━━┛  │
                 │                             │
                 │  Read Only                  │
                 ▼                             │
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
┃         STAGE 2: DECISION ENGINE          ┃  │
┃        (stage2_decision.py)               ┃  │
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫  │
┃                                           ┃  │
┃  Reads from cache (NO recalculation)      ┃  │
┃                                           ┃  │
┃  Decision Logic:                          ┃  │
┃  ┌─────────────────────────────────┐     ┃  │
┃  │ LONG Score Calculation          │     ┃  │
┃  │  - Bullish trend? +25 pts       │     ┃  │
┃  │  - Trend strength > 70? +20 pts │     ┃  │
┃  │  - EMA alignment? +15 pts       │     ┃  │
┃  │  - MACD bullish? +10 pts        │     ┃  │
┃  │  - ADX > 25? +10 pts            │     ┃  │
┃  │  - Multi-TF confirm? +15 pts    │     ┃  │
┃  │  ... etc ...                    │     ┃  │
┃  └─────────────────────────────────┘     ┃  │
┃                                           ┃  │
┃  ┌─────────────────────────────────┐     ┃  │
┃  │ SHORT Score Calculation         │     ┃  │
┃  │  - Bearish trend? +25 pts       │     ┃  │
┃  │  - Bearish EMA? +15 pts         │     ┃  │
┃  │  ... etc ...                    │     ┃  │
┃  └─────────────────────────────────┘     ┃  │
┃                                           ┃  │
┃  Final Decision:                          ┃  │
┃  ┌─────────────────────────────────┐     ┃  │
┃  │ Score >= 70 + Confidence >= 60  │     ┃  │
┃  │ + Risk >= 50 + WinRate >= 45    │     ┃  │
┃  │                                 │     ┃  │
┃  │ → LONG or SHORT                 │     ┃  │
┃  │   + Entry, SL, TP1, TP2, TP3   │     ┃  │
┃  │   + Risk/Reward ratio           │     ┃  │
┃  │   + Reasoning                   │     ┃  │
┃  └─────────────────────────────────┘     ┃  │
┃                                           ┃  │
┃  OR                                       ┃  │
┃                                           ┃  │
┃  ┌─────────────────────────────────┐     ┃  │
┃  │ Score 50-69                     │     ┃  │
┃  │ → WAIT (setup developing)       │     ┃  │
┃  └─────────────────────────────────┘     ┃  │
┃                                           ┃  │
┃  OR                                       ┃  │
┃                                           ┃  │
┃  ┌─────────────────────────────────┐     ┃  │
┃  │ Score < 50 or filters failed    │     ┃  │
┃  │ → NO TRADE                      │     ┃  │
┃  └─────────────────────────────────┘     ┃  │
┃                                           ┃  │
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
                 │                             │
                 └─────────────────────────────┘
                           │
                           ▼
                   Return Decision


## Example: LONG Decision Flow

┌─────────────────────────────────────────────────────────┐
│ Stage 1 Output (Cached)                                 │
├─────────────────────────────────────────────────────────┤
│ trend = "BULLISH"                                       │
│ trend_strength = 85                                     │
│ ema_alignment = "BULLISH"                               │
│ macd_trend = "BULLISH"                                  │
│ macd_crossover = True                                   │
│ rsi = 55 (NEUTRAL)                                      │
│ adx = 32                                                │
│ mtf_alignment = True                                    │
│ profit_factor = 2.5                                     │
│ win_rate = 65                                           │
│ confidence_score = 78                                   │
│ risk_score = 82                                         │
└─────────────────────────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ Stage 2 Decision Logic                                  │
├─────────────────────────────────────────────────────────┤
│ LONG Score:                                             │
│  ✓ Bullish trend           → +25 pts                    │
│  ✓ Strong trend (85)       → +20 pts                    │
│  ✓ Bullish EMA alignment   → +15 pts                    │
│  ✓ MACD bullish            → +10 pts                    │
│  ✓ MACD bullish crossover  → +10 pts                    │
│  ✓ RSI favorable (55)      → +10 pts                    │
│  ✓ ADX > 25 (32)           → +10 pts                    │
│  ✓ Multi-TF confirmation   → +15 pts                    │
│  ✓ High profit factor      → +10 pts                    │
│                                                         │
│ Total Score: 125 → Capped at 95                         │
│                                                         │
│ Filters:                                                │
│  ✓ Confidence >= 60? YES (78)                           │
│  ✓ Risk Score >= 50? YES (82)                           │
│  ✓ Win Rate >= 45? YES (65)                             │
│                                                         │
│ → DECISION: LONG                                        │
└─────────────────────────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ Calculate Trade Setup (ATR-based)                       │
├─────────────────────────────────────────────────────────┤
│ Current Price: 40000                                    │
│ ATR: 500                                                │
│ Mode: INTRADAY                                          │
│                                                         │
│ Entry:     40000                                        │
│ Stop Loss: 39500 (current - 1*ATR)                      │
│ TP1:       40750 (current + 1.5*ATR)                    │
│ TP2:       41000 (current + 2*ATR)                      │
│ TP3:       41500 (current + 3*ATR)                      │
│                                                         │
│ Risk:   500                                             │
│ Reward: 1000                                            │
│ R:R:    2.0                                             │
└─────────────────────────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ Final Response                                          │
├─────────────────────────────────────────────────────────┤
│ {                                                       │
│   "Decision": "LONG",                                   │
│   "Symbol": "BTC-USD",                                  │
│   "Entry": 40000,                                       │
│   "StopLoss": 39500,                                    │
│   "TP1": 40750,                                         │
│   "TP2": 41000,                                         │
│   "TP3": 41500,                                         │
│   "RiskReward": 2.0,                                    │
│   "DecisionConfidence": 95,                             │
│   "Reason": "Bullish trend | Strong trend (85) |       │
│              MACD bullish crossover | Multi-timeframe  │
│              confirmation | High profit factor"         │
│ }                                                       │
└─────────────────────────────────────────────────────────┘
```

## Key Principles

### ✅ DO in Stage 1:
- Calculate ALL technical indicators
- Store EVERYTHING in cache
- Compute market health, confidence, risk
- Generate AI summaries

### ❌ DON'T in Stage 1:
- Make trading decisions
- Filter or select signals
- Return BUY/SELL recommendations

### ✅ DO in Stage 2:
- Read from cache ONLY
- Apply decision logic
- Score LONG/SHORT setups
- Filter based on thresholds
- Calculate entry/stops/targets
- Provide reasoning

### ❌ DON'T in Stage 2:
- Recalculate ANY indicators
- Fetch new data
- Modify the cache
- Access raw DataFrames

## Benefits Summary

```
┌─────────────────────────────────────────────┐
│ Before (Single Stage)                       │
├─────────────────────────────────────────────┤
│ • Calculate indicators                      │
│ • Make decision                             │
│ • Return result                             │
│                                             │
│ Problem: Everything mixed together          │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ After (Two Stage)                           │
├─────────────────────────────────────────────┤
│ Stage 1:                                    │
│ • Calculate indicators ONCE                 │
│ • Store in structured cache                 │
│                                             │
│ Stage 2:                                    │
│ • Read from cache                           │
│ • Apply decision logic                      │
│ • Return ONE clear decision                 │
│                                             │
│ Benefits:                                   │
│ ✓ No redundant calculations                 │
│ ✓ Clean separation of concerns              │
│ ✓ Easy to test independently                │
│ ✓ Full audit trail                          │
│ ✓ Flexible decision strategies              │
└─────────────────────────────────────────────┘
```
