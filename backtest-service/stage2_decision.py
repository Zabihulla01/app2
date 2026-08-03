"""
Stage 2: Decision Engine
-------------------------
Makes trading decisions based ONLY on cached analysis from Stage 1.
NEVER recalculates indicators. Only reads from analysis_cache.

Returns ONE of: LONG, SHORT, WAIT, NO TRADE

If LONG or SHORT:
  - Entry, Stop Loss, TP1, TP2, TP3
  - Risk/Reward ratio
  - Decision confidence
  - Reason for decision
"""

from typing import Dict, Any, Optional
from analysis_cache import get_analysis_cache


def make_trading_decision(symbol: str, mode: str = "INTRADAY") -> Dict[str, Any]:
    """
    Main decision engine function.
    
    Args:
        symbol: Stock/crypto symbol
        mode: "INTRADAY" or "SWING"
    
    Returns:
        Dict with decision, entry, stops, targets, and reasoning
    """
    # Get cached analysis - NEVER recalculate
    cache = get_analysis_cache(symbol)
    
    if not cache:
        return {
            "Decision": "NO TRADE",
            "Reason": "No analysis cache available",
            "Symbol": symbol,
            "Confidence": 0
        }
    
    # Extract key metrics from cache
    trend = cache.get("trend", "NEUTRAL")
    trend_strength = cache.get("trend_strength", 0)
    market_health = cache["market_health"]["overall_score"]
    confidence_score = cache.get("confidence_score", 0)
    risk_score = cache.get("risk_score", 0)
    
    rsi = cache["rsi_analysis"]["rsi"]
    rsi_signal = cache["rsi_analysis"]["signal"]
    
    adx = cache["adx_analysis"]["adx"]
    adx_strength = cache["adx_analysis"]["trend_strength"]
    
    macd_trend = cache["macd_analysis"]["trend"]
    macd_crossover = cache["macd_analysis"]["crossover"]
    
    ema_alignment = cache["ema_analysis"]["alignment"]
    
    mtf_alignment = cache["multi_timeframe_confirmation"]["alignment"]
    
    structure_break = cache.get("structure_break", False)
    
    volatility_regime = cache["volatility_analysis"]["volatility_regime"]
    
    # Backtest metrics
    win_rate = cache["backtest_metrics"]["win_rate"]
    profit_factor = cache["backtest_metrics"]["profit_factor"]
    
    # Decision logic
    decision_result = evaluate_decision(
        trend=trend,
        trend_strength=trend_strength,
        market_health=market_health,
        confidence_score=confidence_score,
        risk_score=risk_score,
        rsi=rsi,
        rsi_signal=rsi_signal,
        adx=adx,
        adx_strength=adx_strength,
        macd_trend=macd_trend,
        macd_crossover=macd_crossover,
        ema_alignment=ema_alignment,
        mtf_alignment=mtf_alignment,
        structure_break=structure_break,
        volatility_regime=volatility_regime,
        win_rate=win_rate,
        profit_factor=profit_factor
    )
    
    decision = decision_result["decision"]
    reasons = decision_result["reasons"]
    decision_confidence = decision_result["confidence"]
    
    # If decision is LONG or SHORT, calculate entry/stops/targets
    if decision in ["LONG", "SHORT"]:
        trade_setup = calculate_trade_setup(cache, decision, mode)
        
        return {
            "Decision": decision,
            "Symbol": symbol,
            "Mode": mode,
            "Entry": trade_setup["entry"],
            "StopLoss": trade_setup["stop_loss"],
            "TP1": trade_setup["tp1"],
            "TP2": trade_setup["tp2"],
            "TP3": trade_setup["tp3"],
            "Risk": trade_setup["risk"],
            "Reward": trade_setup["reward"],
            "RiskReward": trade_setup["risk_reward"],
            "DecisionConfidence": decision_confidence,
            "Confidence": confidence_score,
            "RiskScore": risk_score,
            "Reason": " | ".join(reasons),
            "Timestamp": cache["timestamp"]
        }
    else:
        return {
            "Decision": decision,
            "Symbol": symbol,
            "Mode": mode,
            "DecisionConfidence": decision_confidence,
            "Confidence": confidence_score,
            "RiskScore": risk_score,
            "Reason": " | ".join(reasons),
            "Timestamp": cache["timestamp"]
        }


def evaluate_decision(
    trend: str,
    trend_strength: float,
    market_health: float,
    confidence_score: float,
    risk_score: float,
    rsi: float,
    rsi_signal: str,
    adx: float,
    adx_strength: str,
    macd_trend: str,
    macd_crossover: bool,
    ema_alignment: str,
    mtf_alignment: bool,
    structure_break: bool,
    volatility_regime: str,
    win_rate: float,
    profit_factor: float
) -> Dict[str, Any]:
    """
    Core decision logic using only cached values.
    Returns decision and reasoning.
    """
    reasons = []
    decision = "NO TRADE"
    decision_confidence = 0
    
    # ── LONG CRITERIA ──────────────────────────────────────────────────────
    long_score = 0
    
    if trend == "BULLISH":
        long_score += 25
        reasons.append("Bullish trend")
    
    if trend_strength > 70:
        long_score += 20
        reasons.append(f"Strong trend ({trend_strength})")
    
    if ema_alignment == "BULLISH":
        long_score += 15
        reasons.append("Bullish EMA alignment")
    
    if macd_trend == "BULLISH":
        long_score += 10
        reasons.append("MACD bullish")
    
    if macd_crossover and macd_trend == "BULLISH":
        long_score += 10
        reasons.append("MACD bullish crossover")
    
    if rsi_signal == "OVERSOLD" or (30 < rsi < 70):
        long_score += 10
        reasons.append(f"RSI favorable ({rsi})")
    
    if adx > 25:
        long_score += 10
        reasons.append(f"Strong trend confirmation (ADX {adx})")
    
    if mtf_alignment:
        long_score += 15
        reasons.append("Multi-timeframe confirmation")
    
    if structure_break and trend == "BULLISH":
        long_score += 10
        reasons.append("Bullish structure break")
    
    if profit_factor >= 2.0:
        long_score += 10
        reasons.append(f"High profit factor ({profit_factor})")
    
    # ── SHORT CRITERIA ─────────────────────────────────────────────────────
    short_score = 0
    short_reasons = []
    
    if trend == "BEARISH":
        short_score += 25
        short_reasons.append("Bearish trend")
    
    if trend_strength > 70 and trend == "BEARISH":
        short_score += 20
        short_reasons.append(f"Strong bearish trend ({trend_strength})")
    
    if ema_alignment == "BEARISH":
        short_score += 15
        short_reasons.append("Bearish EMA alignment")
    
    if macd_trend == "BEARISH":
        short_score += 10
        short_reasons.append("MACD bearish")
    
    if macd_crossover and macd_trend == "BEARISH":
        short_score += 10
        short_reasons.append("MACD bearish crossover")
    
    if rsi_signal == "OVERBOUGHT" or (30 < rsi < 70):
        short_score += 10
        short_reasons.append(f"RSI favorable for short ({rsi})")
    
    if adx > 25:
        short_score += 10
        short_reasons.append(f"Strong trend confirmation (ADX {adx})")
    
    if mtf_alignment and trend == "BEARISH":
        short_score += 15
        short_reasons.append("Multi-timeframe bearish confirmation")
    
    if structure_break and trend == "BEARISH":
        short_score += 10
        short_reasons.append("Bearish structure break")
    
    # ── DECISION LOGIC ─────────────────────────────────────────────────────
    
    # Minimum requirements
    min_confidence = 60
    min_risk_score = 50
    min_win_rate = 50
    
    # Check LONG
    if long_score >= 70 and confidence_score >= min_confidence and risk_score >= min_risk_score:
        decision = "LONG"
        decision_confidence = min(long_score, 95)
    
    # Check SHORT
    elif short_score >= 70 and confidence_score >= min_confidence and risk_score >= min_risk_score:
        decision = "SHORT"
        decision_confidence = min(short_score, 95)
        reasons = short_reasons
    
    # WAIT - decent setup but not strong enough
    elif (long_score >= 50 or short_score >= 50) and confidence_score >= 40:
        decision = "WAIT"
        decision_confidence = 50
        reasons.append("Setup developing, waiting for confirmation")
    
    # NO TRADE - nothing interesting
    else:
        decision = "NO TRADE"
        decision_confidence = 20
        reasons = ["Insufficient signal strength", f"Confidence: {confidence_score}", f"Risk Score: {risk_score}"]
    
    # Filter out bad volatility
    if volatility_regime == "HIGH" and decision in ["LONG", "SHORT"]:
        reasons.append("⚠️ High volatility - reduce position size")
    
    # Filter out low probability setups
    if win_rate < 45 and decision in ["LONG", "SHORT"]:
        decision = "NO TRADE"
        reasons = [f"Low historical win rate ({win_rate}%)"]
        decision_confidence = 10
    
    return {
        "decision": decision,
        "reasons": reasons,
        "confidence": decision_confidence
    }


def calculate_trade_setup(cache: Dict[str, Any], decision: str, mode: str) -> Dict[str, Any]:
    """
    Calculate entry, stop loss, and targets based on ATR.
    Uses cached ATR value - does NOT recalculate.
    
    Args:
        cache: Analysis cache dict
        decision: "LONG" or "SHORT"
        mode: "INTRADAY" or "SWING"
    
    Returns:
        Dict with entry, stops, targets, risk/reward
    """
    current_price = cache["current_price"]
    atr = cache["atr"]
    
    # ATR multipliers based on mode
    if mode == "INTRADAY":
        sl_multiplier = 1.0
        tp1_multiplier = 1.5
        tp2_multiplier = 2.0
        tp3_multiplier = 3.0
    else:  # SWING
        sl_multiplier = 2.0
        tp1_multiplier = 3.0
        tp2_multiplier = 4.0
        tp3_multiplier = 6.0
    
    # Calculate levels for LONG
    if decision == "LONG":
        entry = current_price
        stop_loss = round(current_price - (atr * sl_multiplier), 2)
        tp1 = round(current_price + (atr * tp1_multiplier), 2)
        tp2 = round(current_price + (atr * tp2_multiplier), 2)
        tp3 = round(current_price + (atr * tp3_multiplier), 2)
    
    # Calculate levels for SHORT
    else:  # SHORT
        entry = current_price
        stop_loss = round(current_price + (atr * sl_multiplier), 2)
        tp1 = round(current_price - (atr * tp1_multiplier), 2)
        tp2 = round(current_price - (atr * tp2_multiplier), 2)
        tp3 = round(current_price - (atr * tp3_multiplier), 2)
    
    # Calculate risk and reward
    risk = abs(entry - stop_loss)
    reward = abs(tp2 - entry)  # Use TP2 as primary target
    
    risk_reward = round(reward / risk, 2) if risk > 0 else 0
    
    return {
        "entry": round(entry, 2),
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "risk": round(risk, 2),
        "reward": round(reward, 2),
        "risk_reward": risk_reward
    }


def get_decision_summary(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get a quick summary of the decision for a symbol.
    Useful for scanner endpoints.
    """
    cache = get_analysis_cache(symbol)
    
    if not cache:
        return None
    
    return {
        "Symbol": symbol,
        "Trend": cache.get("trend", "NEUTRAL"),
        "Confidence": cache.get("confidence_score", 0),
        "RiskScore": cache.get("risk_score", 0),
        "MarketHealth": cache["market_health"]["overall_score"],
        "ADX": cache["adx_analysis"]["adx"],
        "RSI": cache["rsi_analysis"]["rsi"],
        "Bias": cache["ai_summary"]["bias"]
    }
