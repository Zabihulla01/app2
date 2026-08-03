"""
Stage 1: Technical Analysis
----------------------------
Calculate ALL technical indicators and store in analysis_cache.
NEVER make trading decisions here. Only analyze and store.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from analysis_cache import create_analysis_cache
from indicators import add_indicators
from market_filter import market_trend


def calculate_trend_analysis(df: pd.DataFrame, cache: Dict[str, Any]):
    """
    Analyze trend direction and strength.
    Populates: trend, trend_strength, market_structure, structure_break
    """
    if len(df) < 50:
        return
    
    # Get EMA values
    ema_9 = df["EMA_9"].iloc[-1] if "EMA_9" in df.columns else df["Close"].iloc[-1]
    ema_21 = df["EMA_21"].iloc[-1] if "EMA_21" in df.columns else df["Close"].iloc[-1]
    ema_50 = df["EMA_50"].iloc[-1] if "EMA_50" in df.columns else df["Close"].iloc[-1]
    ema_200 = df["EMA_200"].iloc[-1] if "EMA_200" in df.columns else df["Close"].iloc[-1]
    
    current_price = float(df["Close"].iloc[-1])
    
    # Determine trend
    if ema_9 > ema_21 > ema_50 > ema_200:
        cache["trend"] = "BULLISH"
        cache["market_structure"] = "UPTREND"
        trend_strength = 90
    elif ema_9 > ema_21 > ema_50:
        cache["trend"] = "BULLISH"
        cache["market_structure"] = "UPTREND"
        trend_strength = 70
    elif ema_9 < ema_21 < ema_50 < ema_200:
        cache["trend"] = "BEARISH"
        cache["market_structure"] = "DOWNTREND"
        trend_strength = 90
    elif ema_9 < ema_21 < ema_50:
        cache["trend"] = "BEARISH"
        cache["market_structure"] = "DOWNTREND"
        trend_strength = 70
    else:
        cache["trend"] = "NEUTRAL"
        cache["market_structure"] = "RANGING"
        trend_strength = 30
    
    cache["trend_strength"] = trend_strength
    
    # Check for structure break
    prev_high = df["High"].iloc[-20:-1].max()
    prev_low = df["Low"].iloc[-20:-1].min()
    
    if current_price > prev_high:
        cache["structure_break"] = True
    elif current_price < prev_low:
        cache["structure_break"] = True
    else:
        cache["structure_break"] = False


def calculate_support_resistance(df: pd.DataFrame, cache: Dict[str, Any]):
    """
    Calculate support and resistance levels.
    Populates: support, resistance, support_strength, resistance_strength
    """
    if len(df) < 20:
        return
    
    # Simple support/resistance based on recent swing points
    lookback = min(50, len(df))
    recent_data = df.tail(lookback)
    
    # Find swing highs and lows
    highs = recent_data["High"]
    lows = recent_data["Low"]
    
    # Resistance = recent high
    resistance = float(highs.max())
    
    # Support = recent low
    support = float(lows.min())
    
    current_price = float(df["Close"].iloc[-1])
    
    # Calculate strength based on how many times price touched these levels
    resistance_touches = len(recent_data[recent_data["High"] >= resistance * 0.98])
    support_touches = len(recent_data[recent_data["Low"] <= support * 1.02])
    
    cache["resistance"] = round(resistance, 2)
    cache["support"] = round(support, 2)
    cache["resistance_strength"] = min(resistance_touches * 20, 100)
    cache["support_strength"] = min(support_touches * 20, 100)


def calculate_volume_analysis(df: pd.DataFrame, cache: Dict[str, Any]):
    """
    Analyze volume patterns.
    Populates: volume_analysis dict
    """
    if "Volume" not in df.columns or len(df) < 20:
        return
    
    current_volume = float(df["Volume"].iloc[-1])
    avg_volume = float(df["Volume"].tail(20).mean())
    
    cache["volume_analysis"]["current_volume"] = round(current_volume, 2)
    cache["volume_analysis"]["avg_volume"] = round(avg_volume, 2)
    
    # Volume trend
    recent_vol = df["Volume"].tail(10).mean()
    older_vol = df["Volume"].tail(20).head(10).mean()
    
    if recent_vol > older_vol * 1.2:
        cache["volume_analysis"]["volume_trend"] = "INCREASING"
    elif recent_vol < older_vol * 0.8:
        cache["volume_analysis"]["volume_trend"] = "DECREASING"
    else:
        cache["volume_analysis"]["volume_trend"] = "STABLE"
    
    # Volume spike detection
    if current_volume > avg_volume * 2:
        cache["volume_analysis"]["volume_spike"] = True
    else:
        cache["volume_analysis"]["volume_spike"] = False



def calculate_rsi_analysis(df: pd.DataFrame, cache: Dict[str, Any]):
    """
    Analyze RSI indicator.
    Populates: rsi_analysis dict
    """
    if "RSI" not in df.columns or len(df) < 14:
        return
    
    rsi = float(df["RSI"].iloc[-1])
    cache["rsi_analysis"]["rsi"] = round(rsi, 2)
    
    # RSI signal
    if rsi >= 70:
        cache["rsi_analysis"]["signal"] = "OVERBOUGHT"
    elif rsi <= 30:
        cache["rsi_analysis"]["signal"] = "OVERSOLD"
    else:
        cache["rsi_analysis"]["signal"] = "NEUTRAL"
    
    # Simple divergence detection
    if len(df) >= 20:
        price_trend = df["Close"].iloc[-10:].diff().mean()
        rsi_trend = df["RSI"].iloc[-10:].diff().mean()
        
        # Bearish divergence: price up, RSI down
        if price_trend > 0 and rsi_trend < 0:
            cache["rsi_analysis"]["divergence"] = True
        # Bullish divergence: price down, RSI up
        elif price_trend < 0 and rsi_trend > 0:
            cache["rsi_analysis"]["divergence"] = True
        else:
            cache["rsi_analysis"]["divergence"] = False


def calculate_macd_analysis(df: pd.DataFrame, cache: Dict[str, Any]):
    """
    Analyze MACD indicator.
    Populates: macd_analysis dict
    """
    if "MACD" not in df.columns or len(df) < 26:
        return
    
    macd = float(df["MACD"].iloc[-1])
    signal = float(df["MACD_Signal"].iloc[-1]) if "MACD_Signal" in df.columns else 0.0
    histogram = macd - signal
    
    cache["macd_analysis"]["macd"] = round(macd, 4)
    cache["macd_analysis"]["signal"] = round(signal, 4)
    cache["macd_analysis"]["histogram"] = round(histogram, 4)
    
    # MACD trend
    if macd > signal and histogram > 0:
        cache["macd_analysis"]["trend"] = "BULLISH"
    elif macd < signal and histogram < 0:
        cache["macd_analysis"]["trend"] = "BEARISH"
    else:
        cache["macd_analysis"]["trend"] = "NEUTRAL"
    
    # Crossover detection
    if len(df) >= 2:
        prev_macd = float(df["MACD"].iloc[-2])
        prev_signal = float(df["MACD_Signal"].iloc[-2]) if "MACD_Signal" in df.columns else 0.0
        
        # Bullish crossover
        if prev_macd <= prev_signal and macd > signal:
            cache["macd_analysis"]["crossover"] = True
        # Bearish crossover
        elif prev_macd >= prev_signal and macd < signal:
            cache["macd_analysis"]["crossover"] = True
        else:
            cache["macd_analysis"]["crossover"] = False


def calculate_ema_analysis(df: pd.DataFrame, cache: Dict[str, Any]):
    """
    Analyze EMA alignment and crossovers.
    Populates: ema_analysis dict
    """
    if len(df) < 200:
        return
    
    ema_9 = float(df["EMA_9"].iloc[-1]) if "EMA_9" in df.columns else 0.0
    ema_21 = float(df["EMA_21"].iloc[-1]) if "EMA_21" in df.columns else 0.0
    ema_50 = float(df["EMA_50"].iloc[-1]) if "EMA_50" in df.columns else 0.0
    ema_200 = float(df["EMA_200"].iloc[-1]) if "EMA_200" in df.columns else 0.0
    
    cache["ema_analysis"]["ema_9"] = round(ema_9, 2)
    cache["ema_analysis"]["ema_21"] = round(ema_21, 2)
    cache["ema_analysis"]["ema_50"] = round(ema_50, 2)
    cache["ema_analysis"]["ema_200"] = round(ema_200, 2)
    
    # EMA alignment
    if ema_9 > ema_21 > ema_50 > ema_200:
        cache["ema_analysis"]["alignment"] = "BULLISH"
    elif ema_9 < ema_21 < ema_50 < ema_200:
        cache["ema_analysis"]["alignment"] = "BEARISH"
    else:
        cache["ema_analysis"]["alignment"] = "MIXED"
    
    # Golden Cross / Death Cross
    if len(df) >= 2:
        prev_ema_50 = float(df["EMA_50"].iloc[-2]) if "EMA_50" in df.columns else 0.0
        prev_ema_200 = float(df["EMA_200"].iloc[-2]) if "EMA_200" in df.columns else 0.0
        
        # Golden Cross: 50 crosses above 200
        if prev_ema_50 <= prev_ema_200 and ema_50 > ema_200:
            cache["ema_analysis"]["golden_cross"] = True
        else:
            cache["ema_analysis"]["golden_cross"] = False
        
        # Death Cross: 50 crosses below 200
        if prev_ema_50 >= prev_ema_200 and ema_50 < ema_200:
            cache["ema_analysis"]["death_cross"] = True
        else:
            cache["ema_analysis"]["death_cross"] = False



def calculate_atr_analysis(df: pd.DataFrame, cache: Dict[str, Any]):
    """
    Analyze ATR (volatility).
    Populates: atr_analysis dict
    """
    if "ATR" not in df.columns or len(df) < 14:
        return
    
    atr = float(df["ATR"].iloc[-1])
    current_price = float(df["Close"].iloc[-1])
    
    cache["atr_analysis"]["atr"] = round(atr, 2)
    cache["atr_analysis"]["atr_multiple"] = round(atr / current_price * 100, 2)
    
    # ATR trend (expanding/contracting)
    if len(df) >= 28:
        recent_atr = df["ATR"].tail(14).mean()
        older_atr = df["ATR"].tail(28).head(14).mean()
        
        if recent_atr > older_atr * 1.2:
            cache["atr_analysis"]["volatility_state"] = "EXPANDING"
        elif recent_atr < older_atr * 0.8:
            cache["atr_analysis"]["volatility_state"] = "CONTRACTING"
        else:
            cache["atr_analysis"]["volatility_state"] = "STABLE"


def calculate_bollinger_analysis(df: pd.DataFrame, cache: Dict[str, Any]):
    """
    Analyze Bollinger Bands.
    Populates: bollinger_analysis dict
    """
    if len(df) < 20:
        return
    
    # Calculate Bollinger Bands
    period = 20
    std_dev = 2
    
    sma = df["Close"].rolling(window=period).mean()
    std = df["Close"].rolling(window=period).std()
    
    upper_band = sma + (std * std_dev)
    middle_band = sma
    lower_band = sma - (std * std_dev)
    
    current_price = float(df["Close"].iloc[-1])
    upper = float(upper_band.iloc[-1])
    middle = float(middle_band.iloc[-1])
    lower = float(lower_band.iloc[-1])
    
    cache["bollinger_analysis"]["upper_band"] = round(upper, 2)
    cache["bollinger_analysis"]["middle_band"] = round(middle, 2)
    cache["bollinger_analysis"]["lower_band"] = round(lower, 2)
    
    # Bandwidth
    bandwidth = (upper - lower) / middle * 100
    cache["bollinger_analysis"]["bandwidth"] = round(bandwidth, 2)
    
    # Position
    if current_price >= upper * 0.98:
        cache["bollinger_analysis"]["position"] = "UPPER"
    elif current_price <= lower * 1.02:
        cache["bollinger_analysis"]["position"] = "LOWER"
    else:
        cache["bollinger_analysis"]["position"] = "MIDDLE"
    
    # Squeeze detection (low volatility)
    if bandwidth < 10:
        cache["bollinger_analysis"]["squeeze"] = True
    else:
        cache["bollinger_analysis"]["squeeze"] = False


def calculate_adx_analysis(df: pd.DataFrame, cache: Dict[str, Any]):
    """
    Analyze ADX (trend strength).
    Populates: adx_analysis dict
    """
    if "ADX" not in df.columns or len(df) < 14:
        return
    
    adx = float(df["ADX"].iloc[-1])
    cache["adx_analysis"]["adx"] = round(adx, 2)
    
    # Get +DI and -DI if available
    if "+DI" in df.columns:
        cache["adx_analysis"]["plus_di"] = round(float(df["+DI"].iloc[-1]), 2)
    if "-DI" in df.columns:
        cache["adx_analysis"]["minus_di"] = round(float(df["-DI"].iloc[-1]), 2)
    
    # Trend strength classification
    if adx >= 50:
        cache["adx_analysis"]["trend_strength"] = "STRONG"
    elif adx >= 25:
        cache["adx_analysis"]["trend_strength"] = "MODERATE"
    else:
        cache["adx_analysis"]["trend_strength"] = "WEAK"


def calculate_volatility_analysis(df: pd.DataFrame, cache: Dict[str, Any]):
    """
    Overall volatility regime analysis.
    Populates: volatility_analysis dict
    """
    if "ATR" not in df.columns or len(df) < 14:
        return
    
    atr = float(df["ATR"].iloc[-1])
    avg_atr = float(df["ATR"].tail(14).mean())
    
    # ATR percentile
    atr_percentile = (atr / avg_atr * 100) if avg_atr > 0 else 100
    cache["volatility_analysis"]["atr_percentile"] = round(atr_percentile, 2)
    
    # Volatility regime
    if atr_percentile > 120:
        cache["volatility_analysis"]["volatility_regime"] = "HIGH"
    elif atr_percentile < 80:
        cache["volatility_analysis"]["volatility_regime"] = "LOW"
    else:
        cache["volatility_analysis"]["volatility_regime"] = "MEDIUM"
    
    # Bollinger width from previous calculation
    cache["volatility_analysis"]["bollinger_width"] = cache["bollinger_analysis"]["bandwidth"]


def calculate_market_health(cache: Dict[str, Any]):
    """
    Calculate overall market health score.
    Populates: market_health dict
    """
    # Trend quality (based on trend strength and ADX)
    trend_strength = cache.get("trend_strength", 0)
    adx = cache["adx_analysis"].get("adx", 0)
    
    trend_quality = (trend_strength * 0.6 + min(adx * 2, 100) * 0.4)
    
    # Momentum quality (RSI + MACD)
    rsi = cache["rsi_analysis"].get("rsi", 50)
    rsi_quality = 100 - abs(rsi - 50) * 2  # Closer to 50 = more balanced
    
    macd_trend = cache["macd_analysis"].get("trend", "NEUTRAL")
    macd_quality = 80 if macd_trend != "NEUTRAL" else 40
    
    momentum_quality = (rsi_quality * 0.5 + macd_quality * 0.5)
    
    # Volume quality
    vol_trend = cache["volume_analysis"].get("volume_trend", "STABLE")
    volume_quality = 80 if vol_trend == "INCREASING" else 50
    
    cache["market_health"]["trend_quality"] = round(trend_quality, 2)
    cache["market_health"]["momentum_quality"] = round(momentum_quality, 2)
    cache["market_health"]["volume_quality"] = round(volume_quality, 2)
    
    # Overall score
    overall = (trend_quality * 0.4 + momentum_quality * 0.35 + volume_quality * 0.25)
    cache["market_health"]["overall_score"] = round(overall, 2)


def calculate_liquidity_analysis(df: pd.DataFrame, cache: Dict[str, Any]):
    """
    Analyze liquidity (spread, depth).
    Populates: liquidity_analysis dict
    """
    if len(df) < 10:
        return
    
    # Simple liquidity score based on volume
    avg_volume = cache["volume_analysis"].get("avg_volume", 0)
    
    if avg_volume > 1000000:
        cache["liquidity_analysis"]["liquidity_score"] = 90
        cache["liquidity_analysis"]["depth"] = "HIGH"
    elif avg_volume > 100000:
        cache["liquidity_analysis"]["liquidity_score"] = 60
        cache["liquidity_analysis"]["depth"] = "MEDIUM"
    else:
        cache["liquidity_analysis"]["liquidity_score"] = 30
        cache["liquidity_analysis"]["depth"] = "LOW"
    
    # Spread approximation (High - Low as % of Close)
    current_high = float(df["High"].iloc[-1])
    current_low = float(df["Low"].iloc[-1])
    current_close = float(df["Close"].iloc[-1])
    
    spread = ((current_high - current_low) / current_close * 100) if current_close > 0 else 0
    cache["liquidity_analysis"]["spread"] = round(spread, 2)


def calculate_multi_timeframe_confirmation(df: pd.DataFrame, df_higher: pd.DataFrame, cache: Dict[str, Any]):
    """
    Check multi-timeframe alignment.
    Populates: multi_timeframe_confirmation dict
    """
    if df_higher.empty or len(df_higher) < 2:
        return
    
    # Get higher timeframe trend
    higher_trend = market_trend(df_higher["Close"])
    
    cache["multi_timeframe_confirmation"]["higher_tf_trend"] = "BULLISH" if higher_trend else "BEARISH"
    
    # Check alignment
    current_trend = cache.get("trend", "NEUTRAL")
    
    if higher_trend and current_trend == "BULLISH":
        cache["multi_timeframe_confirmation"]["alignment"] = True
        cache["multi_timeframe_confirmation"]["confirmation_strength"] = 90
    elif not higher_trend and current_trend == "BEARISH":
        cache["multi_timeframe_confirmation"]["alignment"] = True
        cache["multi_timeframe_confirmation"]["confirmation_strength"] = 90
    else:
        cache["multi_timeframe_confirmation"]["alignment"] = False
        cache["multi_timeframe_confirmation"]["confirmation_strength"] = 30


def generate_ai_summary(cache: Dict[str, Any]):
    """
    Generate AI summary based on all analysis.
    Populates: ai_summary dict
    """
    # Determine bias
    trend = cache.get("trend", "NEUTRAL")
    market_health_score = cache["market_health"].get("overall_score", 0)
    
    if trend == "BULLISH" and market_health_score > 60:
        cache["ai_summary"]["bias"] = "BULLISH"
    elif trend == "BEARISH" and market_health_score > 60:
        cache["ai_summary"]["bias"] = "BEARISH"
    else:
        cache["ai_summary"]["bias"] = "NEUTRAL"
    
    # Key factors
    key_factors = []
    
    if cache["trend_strength"] > 70:
        key_factors.append(f"Strong {trend.lower()} trend")
    
    if cache["adx_analysis"]["adx"] > 25:
        key_factors.append(f"ADX {cache['adx_analysis']['adx']} indicates trending market")
    
    if cache["volume_analysis"]["volume_spike"]:
        key_factors.append("Volume spike detected")
    
    if cache["rsi_analysis"]["signal"] == "OVERBOUGHT":
        key_factors.append("RSI overbought")
    elif cache["rsi_analysis"]["signal"] == "OVERSOLD":
        key_factors.append("RSI oversold")
    
    cache["ai_summary"]["key_factors"] = key_factors
    
    # Warnings
    warnings = []
    
    if cache["volatility_analysis"]["volatility_regime"] == "HIGH":
        warnings.append("High volatility environment")
    
    if cache["liquidity_analysis"]["depth"] == "LOW":
        warnings.append("Low liquidity - wide spreads")
    
    if not cache["multi_timeframe_confirmation"]["alignment"]:
        warnings.append("No multi-timeframe confirmation")
    
    cache["ai_summary"]["warnings"] = warnings
    
    # Opportunities
    opportunities = []
    
    if cache["structure_break"]:
        opportunities.append("Structure break detected")
    
    if cache["macd_analysis"]["crossover"]:
        opportunities.append("MACD crossover signal")
    
    if cache["bollinger_analysis"]["squeeze"]:
        opportunities.append("Bollinger squeeze - potential breakout")
    
    cache["ai_summary"]["opportunities"] = opportunities


def run_stage1_analysis(
    symbol: str,
    df: pd.DataFrame,
    df_higher_tf: pd.DataFrame,
    timeframe: str,
    backtest_metrics: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Main function for Stage 1 Analysis.
    
    Args:
        symbol: Stock/crypto symbol
        df: OHLCV DataFrame with indicators
        df_higher_tf: Higher timeframe DataFrame for confirmation
        timeframe: Current timeframe (e.g., "15m", "1h")
        backtest_metrics: Dict with win_rate, profit_factor, sharpe, etc.
    
    Returns:
        Populated analysis cache dict
    """
    # Create cache
    cache = create_analysis_cache(symbol, timeframe)
    
    # Store price and ATR
    cache["current_price"] = round(float(df["Close"].iloc[-1]), 2)
    if "ATR" in df.columns:
        cache["atr"] = round(float(df["ATR"].iloc[-1]), 2)
    
    # Run all analysis functions
    calculate_trend_analysis(df, cache)
    calculate_support_resistance(df, cache)
    calculate_volume_analysis(df, cache)
    calculate_rsi_analysis(df, cache)
    calculate_macd_analysis(df, cache)
    calculate_ema_analysis(df, cache)
    calculate_atr_analysis(df, cache)
    calculate_bollinger_analysis(df, cache)
    calculate_adx_analysis(df, cache)
    calculate_volatility_analysis(df, cache)
    calculate_liquidity_analysis(df, cache)
    calculate_multi_timeframe_confirmation(df, df_higher_tf, cache)
    calculate_market_health(cache)
    generate_ai_summary(cache)
    
    # Store backtest metrics
    cache["backtest_metrics"] = backtest_metrics
    
    # Calculate confidence and risk scores
    cache["confidence_score"] = calculate_confidence_score(cache)
    cache["risk_score"] = calculate_risk_score(cache)
    
    return cache


def calculate_confidence_score(cache: Dict[str, Any]) -> float:
    """Calculate overall confidence score 0-100."""
    market_health = cache["market_health"]["overall_score"]
    trend_strength = cache["trend_strength"]
    mtf_confirmation = cache["multi_timeframe_confirmation"]["confirmation_strength"]
    
    # Backtest performance
    win_rate = cache["backtest_metrics"].get("win_rate", 0)
    profit_factor = cache["backtest_metrics"].get("profit_factor", 0)
    
    backtest_score = min((win_rate + min(profit_factor * 10, 100)) / 2, 100)
    
    confidence = (
        market_health * 0.3 +
        trend_strength * 0.2 +
        mtf_confirmation * 0.2 +
        backtest_score * 0.3
    )
    
    return round(confidence, 2)


def calculate_risk_score(cache: Dict[str, Any]) -> float:
    """Calculate risk score 0-100 (higher = better risk/reward)."""
    profit_factor = cache["backtest_metrics"].get("profit_factor", 0)
    sharpe = cache["backtest_metrics"].get("sharpe_ratio", 0)
    max_dd = cache["backtest_metrics"].get("max_drawdown", 100)
    
    # Risk score formula (from original code)
    pf_score = min(profit_factor * 30, 100)
    sharpe_score = min(abs(sharpe) * 50, 100)
    dd_score = max(0, 100 - max_dd * 2)
    
    risk_score = (pf_score * 0.5 + sharpe_score * 0.3 + dd_score * 0.2)
    
    return round(risk_score, 2)
