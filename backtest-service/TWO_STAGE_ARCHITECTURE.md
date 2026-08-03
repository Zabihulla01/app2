# Two-Stage Analysis Architecture

## Overview

The trading system now uses a **two-stage architecture** that separates technical analysis from decision-making:

- **Stage 1**: Technical Analysis → Calculates ALL indicators and stores in cache
- **Stage 2**: Decision Engine → Reads ONLY from cache and produces trading decisions

## Architecture

```
┌─────────────────┐
│   Stage 1       │
│   Analysis      │ ──> Calculates all technical indicators
└────────┬────────┘     - Trend, RSI, MACD, EMA, ATR, ADX
         │              - Volume, Liquidity, Volatility
         │              - Support/Resistance
         │              - Market Health
         │              - AI Summary
         ▼
┌─────────────────┐
│ Analysis Cache  │ ──> Stores all results (NO recalculation)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Stage 2       │ ──> Makes trading decision
│   Decision      │     - LONG
└─────────────────┘     - SHORT
                        - WAIT
                        - NO TRADE
```

## Modules

### 1. `analysis_cache.py`

Structured cache for all technical analysis results.

**Key Functions:**
- `create_analysis_cache(symbol, timeframe)` - Create new cache
- `get_analysis_cache(symbol)` - Retrieve cached analysis
- `clear_analysis_cache(symbol)` - Clear cache

**Cache Structure:**
```python
{
    "symbol": "BTC-USD",
    "timeframe": "1h",
    "timestamp": "2024-01-01T12:00:00Z",
    "current_price": 40000.0,
    "atr": 500.0,
    "trend": "BULLISH",
    "trend_strength": 85.0,
    "market_structure": "UPTREND",
    "support": 39000.0,
    "resistance": 41000.0,
    "volume_analysis": {...},
    "rsi_analysis": {...},
    "macd_analysis": {...},
    "ema_analysis": {...},
    "bollinger_analysis": {...},
    "adx_analysis": {...},
    "market_health": {...},
    "confidence_score": 75.0,
    "risk_score": 80.0,
    "ai_summary": {...},
    "backtest_metrics": {...}
}
```

### 2. `stage1_analysis.py`

Calculates ALL technical indicators and populates the analysis cache.

**Main Function:**
```python
run_stage1_analysis(
    symbol="BTC-USD",
    df=ohlcv_dataframe,
    df_higher_tf=higher_timeframe_df,
    timeframe="1h",
    backtest_metrics={...}
)
```

**What It Does:**
- Trend analysis (direction, strength, structure)
- Support/Resistance calculation
- Volume analysis (trend, spikes)
- RSI analysis (overbought/oversold, divergence)
- MACD analysis (crossovers, trend)
- EMA alignment (golden/death cross)
- ATR volatility analysis
- Bollinger Bands (squeeze, position)
- ADX trend strength
- Multi-timeframe confirmation
- Market health scoring
- AI summary generation
- Confidence & Risk scoring

### 3. `stage2_decision.py`

Decision engine that reads ONLY from the analysis cache.

**Main Function:**
```python
make_trading_decision(symbol="BTC-USD", mode="INTRADAY")
```

**Returns One Of:**
- **LONG** - Bullish setup with entry/stops/targets
- **SHORT** - Bearish setup with entry/stops/targets
- **WAIT** - Setup developing, needs more confirmation
- **NO TRADE** - No actionable setup

**For LONG/SHORT Decisions:**
```json
{
    "Decision": "LONG",
    "Symbol": "BTC-USD",
    "Mode": "INTRADAY",
    "Entry": 40000.0,
    "StopLoss": 39500.0,
    "TP1": 40750.0,
    "TP2": 41000.0,
    "TP3": 41500.0,
    "Risk": 500.0,
    "Reward": 1000.0,
    "RiskReward": 2.0,
    "DecisionConfidence": 85,
    "Confidence": 75,
    "RiskScore": 80,
    "Reason": "Bullish trend | MACD bullish crossover | Multi-timeframe confirmation"
}
```

## API Endpoints

### New Endpoints

#### `GET /analyze/{stock}?mode=INTRADAY`

Full two-stage analysis pipeline:
1. Runs Stage 1 (calculates all indicators)
2. Runs Stage 2 (makes trading decision)
3. Returns decision with entry/stops/targets

**Example:**
```bash
curl "http://localhost:8000/analyze/BTC-USD?mode=INTRADAY"
```

#### `GET /decision/{stock}?mode=INTRADAY`

Returns cached Stage 2 decision. If no cache exists, runs full analysis.

**Example:**
```bash
curl "http://localhost:8000/decision/BTC-USD?mode=SWING"
```

#### `GET /scanner_v2?mode=INTRADAY`

Scanner using two-stage analysis. Returns top 10 stocks with actionable signals (LONG/SHORT/WAIT).

**Example:**
```bash
curl "http://localhost:8000/scanner_v2?mode=INTRADAY"
```

### Existing Endpoints (Unchanged)

- `GET /backtest/{stock}` - Original backtest (backward compatible)
- `GET /scanner` - Original scanner (backward compatible)
- All other endpoints remain functional

## Decision Logic

### LONG Criteria
- Trend = BULLISH (25 points)
- Trend Strength > 70 (20 points)
- Bullish EMA alignment (15 points)
- MACD bullish (10 points)
- MACD bullish crossover (10 points)
- RSI favorable (10 points)
- ADX > 25 (10 points)
- Multi-timeframe confirmation (15 points)
- Bullish structure break (10 points)
- Profit Factor >= 2.0 (10 points)

**Minimum:** 70 points + Confidence >= 60 + Risk Score >= 50

### SHORT Criteria
- Same scoring but for bearish signals
- Trend = BEARISH
- Bearish EMA alignment
- MACD bearish crossover
- Etc.

### WAIT
- Score 50-69 points
- Confidence >= 40
- Setup developing but needs confirmation

### NO TRADE
- Score < 50
- Or Confidence < 60
- Or Risk Score < 50
- Or Win Rate < 45%

## Benefits

1. **Separation of Concerns**
   - Stage 1: Pure technical analysis
   - Stage 2: Pure decision logic
   
2. **No Redundant Calculations**
   - Indicators calculated once
   - Decision engine reads from cache
   
3. **Easy Testing**
   - Test Stage 1 independently
   - Test Stage 2 with mock cache
   
4. **Flexible Decision Logic**
   - Change decision rules without recalculating indicators
   - A/B test different strategies
   
5. **Audit Trail**
   - Full analysis stored in cache
   - Can review why a decision was made

## Testing

### Test Script

Run the included test script:
```bash
python3 test_two_stage.py
```

This will:
- Test all imports
- Create mock data
- Run Stage 1 analysis
- Run Stage 2 decision
- Display all results

### Manual Testing

1. **Test Analysis:**
```bash
curl "http://localhost:8000/analyze/BTC-USD?mode=INTRADAY" | python3 -m json.tool
```

2. **Test Cached Decision:**
```bash
curl "http://localhost:8000/decision/BTC-USD?mode=INTRADAY" | python3 -m json.tool
```

3. **Test Scanner:**
```bash
curl "http://localhost:8000/scanner_v2?mode=SWING" | python3 -m json.tool
```

## Migration Guide

### Old Code (Single Stage)
```python
# Everything calculated in one place
def backtest(stock):
    df = fetch_data(stock)
    # Calculate indicators
    # Make decision
    # Return everything mixed together
```

### New Code (Two Stage)
```python
# Stage 1: Calculate and cache
cache = run_stage1_analysis(symbol, df, df_higher, timeframe, metrics)

# Stage 2: Read and decide
decision = make_trading_decision(symbol, mode)
```

## Future Enhancements

1. **Persistent Cache** - Store cache in Redis/DB
2. **Cache Expiry** - Auto-refresh stale analysis
3. **Multiple Strategies** - Different decision engines reading same cache
4. **ML Integration** - Feed cache into ML models
5. **Real-time Updates** - WebSocket streaming of cache updates

## Notes

- Original `/backtest` and `/scanner` endpoints remain unchanged for backward compatibility
- All new endpoints are additive, not breaking changes
- Cache is currently in-memory (clears on service restart)
- Test with small stock lists before running full scans

## File Summary

- `analysis_cache.py` - 217 lines - Cache structure and storage
- `stage1_analysis.py` - 623 lines - All technical analysis
- `stage2_decision.py` - 368 lines - Decision engine
- `test_two_stage.py` - 149 lines - Test script
- `main.py` - Modified to add new endpoints

Total: ~1,357 lines of new code
