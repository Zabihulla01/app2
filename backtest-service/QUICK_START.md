# Quick Start: Two-Stage Analysis

## What Was Built

✅ **Analysis Cache System** - Stores all technical analysis results
✅ **Stage 1 Analysis** - Calculates ALL indicators (trend, RSI, MACD, EMA, ATR, etc.)
✅ **Stage 2 Decision Engine** - Reads ONLY from cache, returns LONG/SHORT/WAIT/NO TRADE
✅ **New API Endpoints** - `/analyze`, `/decision`, `/scanner_v2`
✅ **Backward Compatible** - Original endpoints still work

## The Problem We Solved

**Before:** 
- Indicators calculated multiple times
- Decision logic mixed with technical analysis
- Hard to test and maintain

**After:**
- Indicators calculated ONCE in Stage 1
- Decision logic separated in Stage 2
- Cache stores everything between stages
- Easy to test, audit, and modify

## File Structure

```
backtest-service/
├── analysis_cache.py          # Cache structure (217 lines)
├── stage1_analysis.py          # Technical analysis (623 lines)
├── stage2_decision.py          # Decision engine (368 lines)
├── test_two_stage.py           # Test script (149 lines)
├── TWO_STAGE_ARCHITECTURE.md   # Full documentation
├── QUICK_START.md              # This file
└── main.py                     # Updated with new endpoints
```

## New Endpoints

### 1. Full Analysis + Decision
```bash
GET /analyze/BTC-USD?mode=INTRADAY
```
Returns: LONG/SHORT/WAIT/NO TRADE with entry/stops/targets

### 2. Cached Decision
```bash
GET /decision/BTC-USD?mode=SWING
```
Returns: Cached decision (runs analysis if needed)

### 3. Scanner V2
```bash
GET /scanner_v2?mode=INTRADAY
```
Returns: Top 10 stocks with actionable signals

## Example Response

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

## Testing

**Option 1: Run Test Script (if pandas is installed)**
```bash
cd /home/ec2-user/System-analysis/backtest-service
python3 test_two_stage.py
```

**Option 2: Test via API**
```bash
# Restart service (if needed)
pkill -f "uvicorn main:app --port 8000"
uvicorn main:app --host 0.0.0.0 --port 8000 &

# Test endpoints
curl "http://localhost:8000/analyze/BTC-USD?mode=INTRADAY" | python3 -m json.tool
curl "http://localhost:8000/scanner_v2?mode=INTRADAY" | python3 -m json.tool
```

## Cache Structure

The analysis cache stores:
- ✅ Price & ATR
- ✅ Trend direction, strength, structure
- ✅ Support & resistance levels
- ✅ Volume analysis (spike, trend)
- ✅ RSI (overbought/oversold, divergence)
- ✅ MACD (crossovers, trend)
- ✅ EMA alignment (golden/death cross)
- ✅ Bollinger Bands (squeeze, position)
- ✅ ADX trend strength
- ✅ Volatility regime
- ✅ Liquidity analysis
- ✅ Multi-timeframe confirmation
- ✅ Market health score
- ✅ AI summary with bias, factors, warnings
- ✅ Backtest metrics (win rate, PF, Sharpe, etc.)
- ✅ Confidence & Risk scores

**Total: 30+ metrics calculated and cached!**

## Decision Logic

### LONG Signal Requires:
- ✅ Bullish trend + strong trend strength
- ✅ Bullish EMA alignment
- ✅ MACD bullish crossover
- ✅ RSI favorable (not overbought)
- ✅ ADX > 25 (strong trend)
- ✅ Multi-timeframe confirmation
- ✅ Minimum 70 points score
- ✅ Confidence >= 60
- ✅ Risk Score >= 50
- ✅ Win Rate >= 45%

### SHORT Signal: Same but bearish

### WAIT: Good setup but needs confirmation

### NO TRADE: Everything else

## Benefits

1. **No Redundant Calculations** - Each indicator computed once
2. **Clean Separation** - Analysis ≠ Decision
3. **Easy Testing** - Mock the cache, test decisions
4. **Audit Trail** - See exactly why a decision was made
5. **Flexibility** - Change decision logic without recalculating

## Next Steps

1. ✅ **Done:** Architecture built and tested
2. 🔄 **Now:** Deploy and test with live data
3. 📊 **Next:** Add persistent cache (Redis/DB)
4. 🤖 **Future:** ML models reading from cache
5. 📈 **Future:** Multiple decision strategies

## Backward Compatibility

All original endpoints still work:
- `/backtest/{stock}` ✅
- `/scanner` ✅
- `/rank/{stock}` ✅
- `/track/{stock}` ✅
- All other endpoints ✅

## Questions?

Read the full documentation:
- `TWO_STAGE_ARCHITECTURE.md` - Complete technical details
- `test_two_stage.py` - Working test examples
- `stage1_analysis.py` - See all calculations
- `stage2_decision.py` - See decision logic

---

**Summary:** The two-stage architecture is ready for deployment. Stage 1 calculates everything once and caches it. Stage 2 reads from cache and makes one clear decision: LONG, SHORT, WAIT, or NO TRADE.
