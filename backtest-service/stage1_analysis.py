"""
stage1_analysis.py
==================
Advanced Market Intelligence Engine — Stage 1
Analyzes market using all indicators. NEVER makes trade decisions.
Stage 2 reads the output cache and makes the decision.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any
from analysis_cache import create_analysis_cache
from indicators import add_indicators
from market_filter import market_trend


# =============================================================================
# PRICE ACTION
# =============================================================================

def calc_price_action(df: pd.DataFrame, cache: Dict[str, Any]):
    """
    Detect: HH/HL, LH/LL, BOS, CHoCH, Swing High/Low
    """
    if len(df) < 10:
        return

    highs = df["High"].values
    lows  = df["Low"].values
    closes = df["Close"].values
    n = len(closes)

    # Find swing points using 5-bar pivot
    def swing_high(i):
        if i < 2 or i > n - 3:
            return False
        return highs[i] == max(highs[i-2:i+3])

    def swing_low(i):
        if i < 2 or i > n - 3:
            return False
        return lows[i] == min(lows[i-2:i+3])

    swing_highs = [i for i in range(2, n-2) if swing_high(i)]
    swing_lows  = [i for i in range(2, n-2) if swing_low(i)]

    last_sh = float(highs[swing_highs[-1]]) if swing_highs else float(highs[-1])
    last_sl = float(lows[swing_lows[-1]])   if swing_lows  else float(lows[-1])

    prev_sh = float(highs[swing_highs[-2]]) if len(swing_highs) >= 2 else last_sh
    prev_sl = float(lows[swing_lows[-2]])   if len(swing_lows)  >= 2 else last_sl

    # Market structure
    hh = last_sh > prev_sh
    hl = last_sl > prev_sl
    lh = last_sh < prev_sh
    ll = last_sl < prev_sl

    if hh and hl:
        structure = "Higher High / Higher Low"
        structure_bias = "BULLISH"
    elif lh and ll:
        structure = "Lower High / Lower Low"
        structure_bias = "BEARISH"
    elif hh and ll:
        structure = "Higher High / Lower Low"
        structure_bias = "NEUTRAL"
    else:
        structure = "Consolidation"
        structure_bias = "NEUTRAL"

    # BOS — Break of Structure: price closes beyond last swing
    current = float(closes[-1])
    bos = "None"
    if current > prev_sh:
        bos = "BOS Bullish"
    elif current < prev_sl:
        bos = "BOS Bearish"

    # CHoCH — Change of Character: opposite-direction break
    choch = "None"
    if structure_bias == "BULLISH" and current < prev_sl:
        choch = "CHoCH Bearish"
    elif structure_bias == "BEARISH" and current > prev_sh:
        choch = "CHoCH Bullish"

    cache["price_action"] = {
        "swing_high":      round(last_sh, 4),
        "swing_low":       round(last_sl, 4),
        "structure":       structure,
        "structure_bias":  structure_bias,
        "higher_high":     bool(hh),
        "higher_low":      bool(hl),
        "lower_high":      bool(lh),
        "lower_low":       bool(ll),
        "bos":             bos,
        "choch":           choch,
    }


# =============================================================================
# SMART MONEY CONCEPTS (SMC)
# =============================================================================

def calc_smc(df: pd.DataFrame, cache: Dict[str, Any]):
    """
    Detect: Order Blocks, FVG, Liquidity Zones, Liquidity Sweep,
            Breaker Blocks, Mitigation Blocks
    """
    if len(df) < 20:
        return

    highs  = df["High"].values
    lows   = df["Low"].values
    opens  = df["Open"].values
    closes = df["Close"].values
    n = len(closes)

    # ── Order Block ───────────────────────────────────────────────────────
    # Last bearish candle before a bullish impulse (or vice versa)
    ob_bull_price = None
    ob_bear_price = None
    for i in range(n - 10, n - 2):
        if i < 1:
            continue
        # Bullish OB: bearish candle before strong bullish move
        if closes[i] < opens[i] and closes[i+1] > opens[i+1]:
            if closes[i+1] - opens[i+1] > (highs[i+1] - lows[i+1]) * 0.6:
                ob_bull_price = round(float(lows[i]), 4)
        # Bearish OB: bullish candle before strong bearish move
        if closes[i] > opens[i] and closes[i+1] < opens[i+1]:
            if opens[i+1] - closes[i+1] > (highs[i+1] - lows[i+1]) * 0.6:
                ob_bear_price = round(float(highs[i]), 4)

    # ── Fair Value Gap (FVG) ──────────────────────────────────────────────
    # 3-candle pattern: gap between candle[i-2] high and candle[i] low (bullish)
    fvg_bull = None
    fvg_bear = None
    for i in range(2, n):
        # Bullish FVG: low of current > high of 2 bars ago
        if lows[i] > highs[i-2]:
            fvg_bull = round(float((lows[i] + highs[i-2]) / 2), 4)
        # Bearish FVG: high of current < low of 2 bars ago
        if highs[i] < lows[i-2]:
            fvg_bear = round(float((highs[i] + lows[i-2]) / 2), 4)

    # ── Liquidity Zones ────────────────────────────────────────────────────
    # Equal highs/lows = liquidity pool (within 0.1%)
    eq_high = None
    eq_low  = None
    for i in range(n - 20, n - 1):
        for j in range(i + 1, n):
            if abs(highs[i] - highs[j]) / highs[i] < 0.001:
                eq_high = round(float(highs[i]), 4)
            if abs(lows[i] - lows[j]) / max(lows[i], 0.001) < 0.001:
                eq_low = round(float(lows[i]), 4)

    # ── Liquidity Sweep ────────────────────────────────────────────────────
    # Price wicked beyond recent high/low but closed back inside
    current_high = float(highs[-1])
    current_low  = float(lows[-1])
    current_close = float(closes[-1])
    recent_high  = float(max(highs[-10:-1]))
    recent_low   = float(min(lows[-10:-1]))

    liq_sweep = "None"
    if current_high > recent_high and current_close < recent_high:
        liq_sweep = "Bearish Sweep (above highs)"
    elif current_low < recent_low and current_close > recent_low:
        liq_sweep = "Bullish Sweep (below lows)"

    # ── Breaker Block ──────────────────────────────────────────────────────
    # Failed OB that flipped — if price broke through OB, it becomes a breaker
    breaker = "None"
    if ob_bull_price and current_close < ob_bull_price:
        breaker = f"Bearish Breaker @ {ob_bull_price}"
    elif ob_bear_price and current_close > ob_bear_price:
        breaker = f"Bullish Breaker @ {ob_bear_price}"

    # ── Mitigation Block ──────────────────────────────────────────────────
    # Price returns to OB to mitigate (fill) it
    mitigation = "None"
    if ob_bull_price:
        if abs(current_close - ob_bull_price) / ob_bull_price < 0.005:
            mitigation = f"Mitigating Bull OB @ {ob_bull_price}"
    if ob_bear_price:
        if abs(current_close - ob_bear_price) / ob_bear_price < 0.005:
            mitigation = f"Mitigating Bear OB @ {ob_bear_price}"

    cache["smc"] = {
        "order_block_bull":  ob_bull_price,
        "order_block_bear":  ob_bear_price,
        "fvg_bull":          fvg_bull,
        "fvg_bear":          fvg_bear,
        "liquidity_zone_high": eq_high,
        "liquidity_zone_low":  eq_low,
        "liquidity_sweep":   liq_sweep,
        "breaker_block":     breaker,
        "mitigation_block":  mitigation,
    }


# =============================================================================
# TREND ANALYSIS
# =============================================================================

def calc_trend(df: pd.DataFrame, cache: Dict[str, Any]):
    """EMA alignment, Supertrend, ADX, +DI/-DI, Trend Strength Score"""
    if len(df) < 20:
        return

    close = float(df["Close"].iloc[-1])

    ema9   = float(df["EMA_9"].iloc[-1])   if "EMA_9"   in df.columns else close
    ema21  = float(df["EMA_21"].iloc[-1])  if "EMA_21"  in df.columns else close
    ema20  = float(df["EMA_20"].iloc[-1])  if "EMA_20"  in df.columns else close
    ema50  = float(df["EMA_50"].iloc[-1])  if "EMA_50"  in df.columns else close
    ema200 = float(df["EMA_200"].iloc[-1]) if "EMA_200" in df.columns else close

    adx    = float(df["ADX"].iloc[-1])   if "ADX"  in df.columns else 0
    pdi    = float(df["+DI"].iloc[-1])   if "+DI"  in df.columns else 0
    mdi    = float(df["-DI"].iloc[-1])   if "-DI"  in df.columns else 0

    st_dir = int(df["Supertrend_Dir"].iloc[-1]) if "Supertrend_Dir" in df.columns else 0
    st_val = float(df["Supertrend"].iloc[-1])   if "Supertrend"     in df.columns else 0

    # EMA alignment
    if ema20 > ema50 > ema200:
        alignment = "Full Bullish"
        align_score = 100
    elif ema20 > ema50:
        alignment = "Bullish"
        align_score = 75
    elif ema20 < ema50 < ema200:
        alignment = "Full Bearish"
        align_score = 0
    elif ema20 < ema50:
        alignment = "Bearish"
        align_score = 25
    else:
        alignment = "Mixed"
        align_score = 50

    # Price vs EMAs
    above_ema9   = close > ema9
    above_ema21  = close > ema21
    above_ema50  = close > ema50
    above_ema200 = close > ema200

    # Supertrend direction
    supertrend_signal = "Bullish" if st_dir == 1 else "Bearish"

    # ADX trend strength
    if adx >= 40:
        adx_strength = "Very Strong"
    elif adx >= 25:
        adx_strength = "Strong"
    elif adx >= 20:
        adx_strength = "Moderate"
    else:
        adx_strength = "Weak"

    # DI direction
    di_bias = "Bullish" if pdi > mdi else "Bearish"

    # Trend Strength Score 0-100
    score = 0
    score += align_score * 0.3
    score += min(adx * 2, 100) * 0.25
    score += (50 if st_dir == 1 else 0) * 0.2 * 2   # 0 or 40
    score += (50 if pdi > mdi else 0) * 0.25 * 2     # 0 or 50 * 0.25
    trend_score = round(min(score, 100), 1)

    # Overall trend
    bull_count = sum([above_ema9, above_ema21, above_ema50, above_ema200, st_dir == 1, pdi > mdi])
    if bull_count >= 5:
        trend = "BULLISH"
    elif bull_count <= 1:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    cache["trend"] = {
        "direction":        trend,
        "ema_alignment":    alignment,
        "ema9":             round(ema9, 4),
        "ema21":            round(ema21, 4),
        "ema20":            round(ema20, 4),
        "ema50":            round(ema50, 4),
        "ema200":           round(ema200, 4),
        "above_ema9":       above_ema9,
        "above_ema21":      above_ema21,
        "above_ema50":      above_ema50,
        "above_ema200":     above_ema200,
        "supertrend":       supertrend_signal,
        "supertrend_val":   round(st_val, 4),
        "adx":              round(adx, 2),
        "adx_strength":     adx_strength,
        "plus_di":          round(pdi, 2),
        "minus_di":         round(mdi, 2),
        "di_bias":          di_bias,
        "strength_score":   trend_score,
    }


# =============================================================================
# MOMENTUM
# =============================================================================

def calc_momentum(df: pd.DataFrame, cache: Dict[str, Any]):
    """RSI, MACD, StochRSI, CCI, Momentum Score"""
    if len(df) < 14:
        return

    rsi = float(df["RSI"].iloc[-1]) if "RSI" in df.columns else 50

    macd     = float(df["MACD"].iloc[-1])        if "MACD"        in df.columns else 0
    macd_sig = float(df["MACD_Signal"].iloc[-1]) if "MACD_Signal" in df.columns else 0
    macd_hist= float(df["MACD_Hist"].iloc[-1])   if "MACD_Hist"   in df.columns else 0

    srsi_k = float(df["StochRSI_K"].iloc[-1]) if "StochRSI_K" in df.columns else 50
    srsi_d = float(df["StochRSI_D"].iloc[-1]) if "StochRSI_D" in df.columns else 50

    cci = float(df["CCI"].iloc[-1]) if "CCI" in df.columns else 0

    # RSI zone
    if rsi >= 70:   rsi_zone = "Overbought"
    elif rsi >= 60: rsi_zone = "Bullish Zone"
    elif rsi >= 40: rsi_zone = "Neutral"
    elif rsi >= 30: rsi_zone = "Bearish Zone"
    else:           rsi_zone = "Oversold"

    # MACD signal
    macd_cross = "None"
    if len(df) >= 2 and "MACD" in df.columns and "MACD_Signal" in df.columns:
        prev_m = float(df["MACD"].iloc[-2])
        prev_s = float(df["MACD_Signal"].iloc[-2])
        if prev_m <= prev_s and macd > macd_sig:
            macd_cross = "Bullish Cross"
        elif prev_m >= prev_s and macd < macd_sig:
            macd_cross = "Bearish Cross"

    macd_trend = "Bullish" if macd > macd_sig else "Bearish"

    # StochRSI
    if srsi_k >= 80:   srsi_zone = "Overbought"
    elif srsi_k <= 20: srsi_zone = "Oversold"
    else:              srsi_zone = "Neutral"
    srsi_cross = "Bullish" if srsi_k > srsi_d else "Bearish"

    # CCI
    if cci >= 100:    cci_signal = "Overbought"
    elif cci <= -100: cci_signal = "Oversold"
    else:             cci_signal = "Neutral"

    # Momentum Score 0-100
    rsi_score  = rsi if rsi <= 50 else 100 - rsi   # distance from extremes → 0 neutral
    rsi_bull   = rsi / 100 * 50
    macd_bull  = 50 if macd > macd_sig else 0
    srsi_bull  = srsi_k / 100 * 50
    cci_bull   = min(max((cci + 200) / 400 * 100, 0), 100) * 0.5

    mom_score = round((rsi_bull + macd_bull + srsi_bull + cci_bull) / 2.5, 1)
    mom_score = round(min(mom_score, 100), 1)

    if mom_score >= 70:   mom_label = "Strong Bullish"
    elif mom_score >= 55: mom_label = "Bullish"
    elif mom_score >= 45: mom_label = "Neutral"
    elif mom_score >= 30: mom_label = "Bearish"
    else:                 mom_label = "Strong Bearish"

    cache["momentum"] = {
        "rsi":          round(rsi, 2),
        "rsi_zone":     rsi_zone,
        "macd":         round(macd, 4),
        "macd_signal":  round(macd_sig, 4),
        "macd_hist":    round(macd_hist, 4),
        "macd_trend":   macd_trend,
        "macd_cross":   macd_cross,
        "stochrsi_k":   round(srsi_k, 2),
        "stochrsi_d":   round(srsi_d, 2),
        "stochrsi_zone": srsi_zone,
        "stochrsi_cross": srsi_cross,
        "cci":          round(cci, 2),
        "cci_signal":   cci_signal,
        "score":        mom_score,
        "label":        mom_label,
    }


# =============================================================================
# VOLATILITY
# =============================================================================

def calc_volatility(df: pd.DataFrame, cache: Dict[str, Any]):
    """ATR, Bollinger Bands, Keltner Channels, Historical Volatility"""
    if len(df) < 20:
        return

    close = float(df["Close"].iloc[-1])
    atr   = float(df["ATR"].iloc[-1]) if "ATR" in df.columns else 0

    bb_upper  = float(df["BB_Upper"].iloc[-1])  if "BB_Upper"  in df.columns else close
    bb_mid    = float(df["BB_Middle"].iloc[-1]) if "BB_Middle" in df.columns else close
    bb_lower  = float(df["BB_Lower"].iloc[-1])  if "BB_Lower"  in df.columns else close
    bb_width  = float(df["BB_Width"].iloc[-1])  if "BB_Width"  in df.columns else 0

    kc_upper  = float(df["KC_Upper"].iloc[-1])  if "KC_Upper"  in df.columns else close
    kc_lower  = float(df["KC_Lower"].iloc[-1])  if "KC_Lower"  in df.columns else close

    # BB position
    if close >= bb_upper * 0.99:   bb_pos = "Above Upper Band"
    elif close <= bb_lower * 1.01: bb_pos = "Below Lower Band"
    elif close >= bb_mid:          bb_pos = "Upper Half"
    else:                          bb_pos = "Lower Half"

    # BB squeeze: BB inside Keltner
    squeeze = (bb_upper < kc_upper) and (bb_lower > kc_lower)

    # Historical Volatility (20-day std of log returns, annualized)
    if len(df) >= 21:
        log_ret = np.log(df["Close"] / df["Close"].shift(1)).dropna()
        hv = float(log_ret.tail(20).std() * np.sqrt(365) * 100)
    else:
        hv = 0.0

    atr_pct = round(atr / close * 100, 2) if close else 0

    if atr_pct >= 5:    vol_regime = "Extreme"
    elif atr_pct >= 2.5: vol_regime = "High"
    elif atr_pct >= 1:  vol_regime = "Moderate"
    else:               vol_regime = "Low"

    # ATR expanding/contracting
    if len(df) >= 28 and "ATR" in df.columns:
        recent_atr = df["ATR"].tail(14).mean()
        older_atr  = df["ATR"].tail(28).head(14).mean()
        if recent_atr > older_atr * 1.15:   atr_state = "Expanding"
        elif recent_atr < older_atr * 0.85: atr_state = "Contracting"
        else:                                atr_state = "Stable"
    else:
        atr_state = "Stable"

    cache["volatility"] = {
        "atr":          round(atr, 4),
        "atr_pct":      atr_pct,
        "atr_state":    atr_state,
        "regime":       vol_regime,
        "bb_upper":     round(bb_upper, 4),
        "bb_middle":    round(bb_mid, 4),
        "bb_lower":     round(bb_lower, 4),
        "bb_width":     round(bb_width, 2),
        "bb_position":  bb_pos,
        "bb_squeeze":   squeeze,
        "kc_upper":     round(kc_upper, 4),
        "kc_lower":     round(kc_lower, 4),
        "hist_vol":     round(hv, 2),
    }


# =============================================================================
# VOLUME ANALYSIS
# =============================================================================

def calc_volume(df: pd.DataFrame, cache: Dict[str, Any]):
    """Volume Trend, RVOL, Spike, Buy/Sell Pressure, VWAP"""
    if "Volume" not in df.columns or len(df) < 10:
        return

    vol     = df["Volume"]
    close   = df["Close"]
    high    = df["High"]
    low     = df["Low"]

    current_vol = float(vol.iloc[-1])
    avg_vol     = float(vol.tail(20).mean())
    rvol        = round(current_vol / avg_vol, 2) if avg_vol > 0 else 1.0

    # Volume trend
    recent  = vol.tail(10).mean()
    older   = vol.tail(20).head(10).mean()
    if recent > older * 1.2:    vol_trend = "Increasing"
    elif recent < older * 0.8:  vol_trend = "Decreasing"
    else:                        vol_trend = "Stable"

    # Spike
    spike = rvol >= 2.0

    # Buy vs Sell Pressure (based on close position in candle range)
    ranges = high - low
    buy_pressure  = 0.0
    sell_pressure = 0.0
    for i in range(-10, 0):
        r = float(ranges.iloc[i])
        if r > 0:
            close_pos = (float(close.iloc[i]) - float(low.iloc[i])) / r
            buy_pressure  += close_pos
            sell_pressure += (1 - close_pos)
    total = buy_pressure + sell_pressure
    buy_pct  = round(buy_pressure / total * 100, 1)  if total else 50
    sell_pct = round(sell_pressure / total * 100, 1) if total else 50

    # VWAP
    vwap = float(df["VWAP"].iloc[-1]) if "VWAP" in df.columns else float(close.iloc[-1])
    price_vs_vwap = "Above VWAP" if float(close.iloc[-1]) > vwap else "Below VWAP"

    cache["volume"] = {
        "current":       round(current_vol, 2),
        "avg_20":        round(avg_vol, 2),
        "rvol":          rvol,
        "trend":         vol_trend,
        "spike":         spike,
        "buy_pressure":  buy_pct,
        "sell_pressure": sell_pct,
        "vwap":          round(vwap, 4),
        "price_vs_vwap": price_vs_vwap,
    }


# =============================================================================
# MARKET HEALTH
# =============================================================================

def calc_market_health(cache: Dict[str, Any]):
    """Bull/Bear/Neutral scores, Overall Health label"""
    trend_score = cache.get("trend", {}).get("strength_score", 50)
    mom_score   = cache.get("momentum", {}).get("score", 50)
    trend_dir   = cache.get("trend", {}).get("direction", "NEUTRAL")
    vol_regime  = cache.get("volatility", {}).get("regime", "Moderate")
    rvol        = cache.get("volume", {}).get("rvol", 1.0)
    adx         = cache.get("trend", {}).get("adx", 0)

    # Bull / Bear scores
    bull_score = 0
    bear_score = 0

    if trend_dir == "BULLISH":
        bull_score += 40
    elif trend_dir == "BEARISH":
        bear_score += 40

    bull_score += trend_score * 0.2
    bear_score += (100 - trend_score) * 0.2

    if mom_score >= 55:
        bull_score += (mom_score - 50) * 0.6
    else:
        bear_score += (50 - mom_score) * 0.6

    if rvol > 1.5:
        if trend_dir == "BULLISH": bull_score += 10
        else: bear_score += 10

    bull_score = round(min(bull_score, 100), 1)
    bear_score = round(min(bear_score, 100), 1)
    neutral_score = round(max(0, 100 - bull_score - bear_score), 1)

    # Penalty for extreme volatility
    vol_penalty = 20 if vol_regime == "Extreme" else 5 if vol_regime == "High" else 0

    overall = max(bull_score, bear_score) - vol_penalty
    overall = round(min(max(overall, 0), 100), 1)

    if overall >= 75:   health_label = "Excellent"
    elif overall >= 55: health_label = "Good"
    elif overall >= 35: health_label = "Weak"
    else:               health_label = "Dangerous"

    cache["market_health"] = {
        "bull_score":    bull_score,
        "bear_score":    bear_score,
        "neutral_score": neutral_score,
        "overall_score": overall,
        "label":         health_label,
    }


# =============================================================================
# MULTI TIMEFRAME
# =============================================================================

def calc_multi_timeframe(dfs: Dict[str, pd.DataFrame], cache: Dict[str, Any]):
    """
    Analyze 5m, 15m, 1h, 4h, 1D timeframes.
    dfs: dict of {timeframe_str: DataFrame}
    """
    results = {}
    for tf, df in dfs.items():
        if df is None or df.empty or len(df) < 20:
            results[tf] = "Neutral"
            continue

        df = add_indicators(df)
        close  = float(df["Close"].iloc[-1])
        ema9   = float(df["EMA_9"].iloc[-1])   if "EMA_9"   in df.columns else close
        ema21  = float(df["EMA_21"].iloc[-1])  if "EMA_21"  in df.columns else close
        ema50  = float(df["EMA_50"].iloc[-1])  if "EMA_50"  in df.columns else close
        adx    = float(df["ADX"].iloc[-1])     if "ADX"     in df.columns else 0
        pdi    = float(df["+DI"].iloc[-1])     if "+DI"     in df.columns else 0
        mdi    = float(df["-DI"].iloc[-1])     if "-DI"     in df.columns else 0
        st_dir = int(df["Supertrend_Dir"].iloc[-1]) if "Supertrend_Dir" in df.columns else 0

        bull = sum([close > ema9, close > ema21, close > ema50, pdi > mdi, st_dir == 1])
        if bull >= 4:      results[tf] = "Bullish"
        elif bull <= 1:    results[tf] = "Bearish"
        else:              results[tf] = "Neutral"

    # Alignment score
    bull_tfs    = sum(1 for v in results.values() if v == "Bullish")
    bear_tfs    = sum(1 for v in results.values() if v == "Bearish")
    total_tfs   = len(results) or 1
    align_score = round(max(bull_tfs, bear_tfs) / total_tfs * 100, 1)

    if bull_tfs > bear_tfs:   overall_bias = "Bullish"
    elif bear_tfs > bull_tfs: overall_bias = "Bearish"
    else:                      overall_bias = "Neutral"

    cache["multi_timeframe"] = {
        "timeframes":    results,
        "overall_bias":  overall_bias,
        "alignment_score": align_score,
        "bull_count":    bull_tfs,
        "bear_count":    bear_tfs,
    }


# =============================================================================
# AI CONFIDENCE
# =============================================================================

def calc_confidence(cache: Dict[str, Any], backtest: Dict[str, Any]):
    """
    Calculate AI Confidence 0-100, Grade A+/A/B/C/D, and explanation.
    """
    trend_score = cache.get("trend", {}).get("strength_score", 0)
    mom_score   = cache.get("momentum", {}).get("score", 50)
    health      = cache.get("market_health", {}).get("overall_score", 0)
    mtf_align   = cache.get("multi_timeframe", {}).get("alignment_score", 0)
    pa          = cache.get("price_action", {})
    smc         = cache.get("smc", {})
    volume      = cache.get("volume", {})

    win_rate = backtest.get("win_rate", 0) or 0
    pf       = backtest.get("profit_factor", 0) or 0
    sharpe   = backtest.get("sharpe", 0) or 0

    bt_score = min((win_rate * 0.5 + min(pf * 20, 50) + min(abs(sharpe) * 10, 30)) / 1.3, 100)

    # Include structure, SMC and volume so confidence reflects all Stage 1
    # evidence, not only trend/momentum/backtest metrics.
    structure_score = 50
    if pa.get("structure_bias") in ("BULLISH", "BEARISH"):
        structure_score = 75
    if pa.get("bos", "None") != "None":
        structure_score += 10
    if pa.get("choch", "None") != "None":
        structure_score -= 10
    smc_score = 50
    if smc.get("liquidity_sweep", "None") != "None":
        smc_score += 15
    if any(smc.get(k) is not None for k in ("order_block_bull", "order_block_bear", "fvg_bull", "fvg_bear")):
        smc_score += 10
    volume_score = min(max(float(volume.get("rvol", 1.0)) * 35, 0), 100)

    confidence = (
        trend_score     * 0.20 +
        mom_score       * 0.15 +
        health          * 0.15 +
        mtf_align       * 0.15 +
        structure_score * 0.10 +
        smc_score       * 0.10 +
        volume_score    * 0.05 +
        bt_score        * 0.10
    )
    confidence = round(min(max(confidence, 0), 100), 1)

    # Grade
    if confidence >= 85:   grade = "A+"
    elif confidence >= 75: grade = "A"
    elif confidence >= 60: grade = "B"
    elif confidence >= 45: grade = "C"
    else:                   grade = "D"

    # Explanation
    reasons = []
    if trend_score >= 70:
        reasons.append(f"Strong trend alignment ({trend_score:.0f}/100)")
    elif trend_score < 40:
        reasons.append(f"Weak trend ({trend_score:.0f}/100)")

    if mom_score >= 65:
        reasons.append(f"Bullish momentum ({mom_score:.0f}/100)")
    elif mom_score <= 35:
        reasons.append(f"Bearish momentum ({mom_score:.0f}/100)")

    if mtf_align >= 70:
        reasons.append(f"Multi-TF aligned ({mtf_align:.0f}%)")
    elif mtf_align < 50:
        reasons.append(f"Conflicting timeframes ({mtf_align:.0f}%)")

    if pa.get("bos", "None") != "None":
        reasons.append(f"Price structure: {pa['bos']}")
    if smc.get("liquidity_sweep", "None") != "None":
        reasons.append(f"SMC liquidity event: {smc['liquidity_sweep']}")
    reasons.append(f"Volume participation: RVOL {float(volume.get('rvol', 1.0)):.2f}x")

    if win_rate >= 55:
        reasons.append(f"Good backtest win rate ({win_rate:.0f}%)")
    elif win_rate < 40:
        reasons.append(f"Poor backtest performance ({win_rate:.0f}%)")

    cache["confidence"] = {
        "score":       confidence,
        "grade":       grade,
        "explanation": reasons,
    }


# =============================================================================
# RISK ANALYSIS
# =============================================================================

def calc_risk(df: pd.DataFrame, cache: Dict[str, Any], backtest: Dict[str, Any]):
    """
    Risk Score 0-100, Position Size, Max Risk%, Leverage, Category
    """
    atr      = cache.get("volatility", {}).get("atr", 0)
    vol_reg  = cache.get("volatility", {}).get("regime", "Moderate")
    health   = cache.get("market_health", {}).get("overall_score", 50)
    max_dd   = backtest.get("max_drawdown", 20) or 20
    pf       = backtest.get("profit_factor", 1) or 1
    sharpe   = backtest.get("sharpe", 0) or 0
    conf     = cache.get("confidence", {}).get("score", 50)

    close = float(df["Close"].iloc[-1]) if len(df) > 0 else 1

    # Risk score (higher = worse risk conditions)
    risk = 0
    if vol_reg == "Extreme":   risk += 35
    elif vol_reg == "High":    risk += 20
    elif vol_reg == "Moderate":risk += 10

    risk += min(max_dd * 1.5, 30)
    risk += max(0, (50 - conf) * 0.4)
    if pf < 1.0: risk += 15
    if sharpe < 0: risk += 10

    risk_score = round(min(max(risk, 0), 100), 1)

    if risk_score <= 25:    risk_category = "Low"
    elif risk_score <= 50:  risk_category = "Moderate"
    elif risk_score <= 75:  risk_category = "High"
    else:                   risk_category = "Very High"

    # Position sizing (% of capital)
    base_pos = 5.0
    if risk_score <= 25:    pos_size = base_pos * 1.5
    elif risk_score <= 50:  pos_size = base_pos
    elif risk_score <= 75:  pos_size = base_pos * 0.6
    else:                   pos_size = base_pos * 0.3
    pos_size = round(pos_size, 1)

    # Max risk per trade
    max_risk_pct = round(min(1.0 + (100 - risk_score) / 50, 3.0), 1)

    # Suggested leverage
    if risk_score <= 25:    leverage = "3x–5x"
    elif risk_score <= 50:  leverage = "2x–3x"
    elif risk_score <= 75:  leverage = "1x–2x"
    else:                   leverage = "1x (Spot only)"

    cache["risk"] = {
        "score":         risk_score,
        "category":      risk_category,
        "position_size": pos_size,
        "max_risk_pct":  max_risk_pct,
        "leverage":      leverage,
    }


# =============================================================================
# AI SUMMARY
# =============================================================================

def calc_summary(cache: Dict[str, Any]):
    """
    Market Bias, Strength, Probability, Recommendation Status.
    Never recommends a trade — analysis only.
    """
    trend_dir  = cache.get("trend", {}).get("direction", "NEUTRAL")
    conf       = cache.get("confidence", {}).get("score", 50)
    health_lbl = cache.get("market_health", {}).get("label", "Weak")
    mtf_bias   = cache.get("multi_timeframe", {}).get("overall_bias", "Neutral")
    risk_cat   = cache.get("risk", {}).get("category", "High")
    bos        = cache.get("price_action", {}).get("bos", "None")
    vol_reg    = cache.get("volatility", {}).get("regime", "Moderate")

    # Market Bias
    votes = [trend_dir, mtf_bias.upper()]
    bull_v = votes.count("BULLISH")
    bear_v = votes.count("BEARISH")
    if bull_v > bear_v:   bias = "Bullish"
    elif bear_v > bull_v: bias = "Bearish"
    else:                 bias = "Neutral"

    # Strength
    trend_score = cache.get("trend", {}).get("strength_score", 0)
    if trend_score >= 70:   strength = "Strong"
    elif trend_score >= 45: strength = "Moderate"
    else:                   strength = "Weak"

    # Probability
    probability = round(conf * 0.7 + (trend_score * 0.3), 1)
    probability = round(min(max(probability, 10), 95), 1)

    # Ready for Stage 2?
    ready = (
        conf >= 50 and
        health_lbl in ("Excellent", "Good") and
        risk_cat not in ("Very High",) and
        vol_reg not in ("Extreme",)
    )
    status = "Ready for Stage 2" if ready else "Wait for Better Setup"

    # Key highlights
    highlights = []
    if bos != "None":
        highlights.append(f"Structure: {bos}")
    choch = cache.get("price_action", {}).get("choch", "None")
    if choch != "None":
        highlights.append(f"Character change: {choch}")
    liq_sweep = cache.get("smc", {}).get("liquidity_sweep", "None")
    if liq_sweep != "None":
        highlights.append(f"Liquidity: {liq_sweep}")
    if cache.get("volatility", {}).get("bb_squeeze", False):
        highlights.append("Bollinger Squeeze — breakout imminent")
    macd_cross = cache.get("momentum", {}).get("macd_cross", "None")
    if macd_cross != "None":
        highlights.append(f"MACD: {macd_cross}")

    cache["summary"] = {
        "bias":        bias,
        "strength":    strength,
        "probability": probability,
        "status":      status,
        "highlights":  highlights,
    }


# =============================================================================
# MAIN RUNNER
# =============================================================================

def run_stage1_analysis(
    symbol: str,
    df: pd.DataFrame,
    df_higher_tf: pd.DataFrame,
    timeframe: str,
    backtest_metrics: Dict[str, Any],
    multi_tf_dfs: Dict[str, pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Run full Stage 1 Advanced Market Intelligence Analysis.

    Parameters
    ----------
    symbol         : e.g. "BTC-USD"
    df             : primary OHLCV DataFrame with indicators added
    df_higher_tf   : higher timeframe DataFrame (for legacy compat)
    timeframe      : primary timeframe string
    backtest_metrics: dict from backtest engine
    multi_tf_dfs   : dict of {tf: DataFrame} for all timeframes

    Returns
    -------
    Flat dict — all fields the Stage 1 route and UI need.
    """
    cache = create_analysis_cache(symbol, timeframe)

    if df.empty or len(df) < 20:
        return cache

    # Add indicators to primary df
    df = add_indicators(df)

    current_price = float(df["Close"].iloc[-1])
    cache["current_price"] = round(current_price, 4)

    # Run all analysis sections
    calc_price_action(df, cache)
    calc_smc(df, cache)
    calc_trend(df, cache)
    calc_momentum(df, cache)
    calc_volatility(df, cache)
    calc_volume(df, cache)

    # Multi-timeframe (use provided dfs or fall back to higher_tf only)
    if multi_tf_dfs:
        calc_multi_timeframe(multi_tf_dfs, cache)
    else:
        fallback = {"1h": df, "1D": df_higher_tf} if df_higher_tf is not None and not df_higher_tf.empty else {"1h": df}
        calc_multi_timeframe(fallback, cache)

    calc_market_health(cache)
    calc_confidence(cache, backtest_metrics)
    calc_risk(df, cache, backtest_metrics)
    calc_summary(cache)

    # Support / Resistance from df
    support    = float(df["SUPPORT"].iloc[-1])    if "SUPPORT"    in df.columns else 0
    resistance = float(df["RESISTANCE"].iloc[-1]) if "RESISTANCE" in df.columns else 0
    cache["support"]    = round(support, 4)
    cache["resistance"] = round(resistance, 4)

    return cache
