#!/usr/bin/env python3
"""
Test script for two-stage analysis architecture
"""

import sys
import pandas as pd
import numpy as np

# Test imports
print("Testing imports...")
try:
    from analysis_cache import create_analysis_cache, get_analysis_cache
    print("✓ analysis_cache imported")
except Exception as e:
    print(f"✗ analysis_cache import failed: {e}")
    sys.exit(1)

try:
    from stage1_analysis import run_stage1_analysis
    print("✓ stage1_analysis imported")
except Exception as e:
    print(f"✗ stage1_analysis import failed: {e}")
    sys.exit(1)

try:
    from stage2_decision import make_trading_decision
    print("✓ stage2_decision imported")
except Exception as e:
    print(f"✗ stage2_decision import failed: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("Testing Analysis Cache")
print("="*60)

# Test cache creation
cache = create_analysis_cache("TEST-USD", "1h")
print(f"✓ Cache created for TEST-USD")
print(f"  Symbol: {cache['symbol']}")
print(f"  Timeframe: {cache['timeframe']}")
print(f"  Timestamp: {cache['timestamp']}")

# Test cache retrieval
retrieved = get_analysis_cache("TEST-USD")
print(f"✓ Cache retrieved")
print(f"  Cache exists: {retrieved is not None}")

print("\n" + "="*60)
print("Testing Stage 1 Analysis (with mock data)")
print("="*60)

# Create mock DataFrame
dates = pd.date_range(start='2024-01-01', periods=200, freq='1H')
np.random.seed(42)
close_prices = 40000 + np.cumsum(np.random.randn(200) * 100)

df = pd.DataFrame({
    'Open': close_prices + np.random.randn(200) * 50,
    'High': close_prices + abs(np.random.randn(200) * 100),
    'Low': close_prices - abs(np.random.randn(200) * 100),
    'Close': close_prices,
    'Volume': np.random.randint(1000, 10000, 200)
}, index=dates)

# Add basic indicators
df['RSI'] = 50 + np.sin(np.arange(200) / 10) * 20
df['MACD'] = np.sin(np.arange(200) / 15) * 100
df['MACD_Signal'] = np.sin(np.arange(200) / 15 - 0.5) * 100
df['EMA_9'] = df['Close'].ewm(span=9).mean()
df['EMA_21'] = df['Close'].ewm(span=21).mean()
df['EMA_50'] = df['Close'].ewm(span=50).mean()
df['EMA_200'] = df['Close'].ewm(span=200).mean()
df['ADX'] = 30 + np.random.randn(200) * 5
df['+DI'] = 25 + np.random.randn(200) * 5
df['-DI'] = 20 + np.random.randn(200) * 5

# Calculate ATR
high_low = df['High'] - df['Low']
high_close = abs(df['High'] - df['Close'].shift())
low_close = abs(df['Low'] - df['Close'].shift())
tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
df['ATR'] = tr.rolling(14).mean()

print(f"✓ Mock DataFrame created: {len(df)} rows")
print(f"  Columns: {list(df.columns)}")

# Mock backtest metrics
backtest_metrics = {
    "win_rate": 65.5,
    "profit_factor": 2.3,
    "sharpe_ratio": 1.5,
    "max_drawdown": 15.2,
    "total_trades": 50,
    "net_profit": 1250.0
}

# Run Stage 1
try:
    cache = run_stage1_analysis(
        symbol="BTC-USD",
        df=df,
        df_higher_tf=df,  # Use same data for higher TF
        timeframe="1h",
        backtest_metrics=backtest_metrics
    )
    print("✓ Stage 1 analysis completed")
    print(f"  Trend: {cache.get('trend')}")
    print(f"  Trend Strength: {cache.get('trend_strength')}")
    print(f"  Confidence Score: {cache.get('confidence_score')}")
    print(f"  Risk Score: {cache.get('risk_score')}")
    print(f"  Market Health: {cache['market_health']['overall_score']}")
    print(f"  AI Bias: {cache['ai_summary']['bias']}")
except Exception as e:
    print(f"✗ Stage 1 analysis failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*60)
print("Testing Stage 2 Decision Engine")
print("="*60)

try:
    decision = make_trading_decision("BTC-USD", mode="INTRADAY")
    print("✓ Stage 2 decision completed")
    print(f"  Decision: {decision.get('Decision')}")
    print(f"  Symbol: {decision.get('Symbol')}")
    print(f"  Confidence: {decision.get('Confidence')}")
    print(f"  Decision Confidence: {decision.get('DecisionConfidence')}")
    
    if decision.get('Decision') in ['LONG', 'SHORT']:
        print(f"  Entry: {decision.get('Entry')}")
        print(f"  Stop Loss: {decision.get('StopLoss')}")
        print(f"  TP1: {decision.get('TP1')}")
        print(f"  TP2: {decision.get('TP2')}")
        print(f"  TP3: {decision.get('TP3')}")
        print(f"  Risk/Reward: {decision.get('RiskReward')}")
    
    print(f"  Reason: {decision.get('Reason')}")
except Exception as e:
    print(f"✗ Stage 2 decision failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*60)
print("✅ ALL TESTS PASSED")
print("="*60)
