"""
analysis_cache.py
=================
Stores all Stage 1 analysis results.
Stage 2 reads ONLY from this cache — never recalculates.
"""

from datetime import datetime
from typing import Dict, Any, Optional
import json


def create_analysis_cache(symbol: str, timeframe: str) -> Dict[str, Any]:
    """
    Create and return a fresh analysis cache for a symbol.
    All sections match the new Stage 1 Advanced Intelligence Engine.
    """
    return {
        # ── Metadata ──────────────────────────────────────────────────────
        "symbol":        symbol,
        "timeframe":     timeframe,
        "timestamp":     datetime.utcnow().isoformat() + "Z",
        "current_price": 0.0,
        "support":       0.0,
        "resistance":    0.0,

        # ── Price Action ──────────────────────────────────────────────────
        "price_action": {
            "swing_high":     0.0,
            "swing_low":      0.0,
            "structure":      "N/A",
            "structure_bias": "NEUTRAL",
            "higher_high":    False,
            "higher_low":     False,
            "lower_high":     False,
            "lower_low":      False,
            "bos":            "None",
            "choch":          "None",
        },

        # ── Smart Money Concepts ──────────────────────────────────────────
        "smc": {
            "order_block_bull":    None,
            "order_block_bear":    None,
            "fvg_bull":            None,
            "fvg_bear":            None,
            "liquidity_zone_high": None,
            "liquidity_zone_low":  None,
            "liquidity_sweep":     "None",
            "breaker_block":       "None",
            "mitigation_block":    "None",
        },

        # ── Trend Analysis ────────────────────────────────────────────────
        "trend": {
            "direction":      "NEUTRAL",
            "ema_alignment":  "Mixed",
            "ema9":           0.0,
            "ema21":          0.0,
            "ema50":          0.0,
            "ema200":         0.0,
            "above_ema9":     False,
            "above_ema21":    False,
            "above_ema50":    False,
            "above_ema200":   False,
            "supertrend":     "N/A",
            "supertrend_val": 0.0,
            "adx":            0.0,
            "adx_strength":   "Weak",
            "plus_di":        0.0,
            "minus_di":       0.0,
            "di_bias":        "Neutral",
            "strength_score": 0.0,
        },

        # ── Momentum ──────────────────────────────────────────────────────
        "momentum": {
            "rsi":            50.0,
            "rsi_zone":       "Neutral",
            "macd":           0.0,
            "macd_signal":    0.0,
            "macd_hist":      0.0,
            "macd_trend":     "Neutral",
            "macd_cross":     "None",
            "stochrsi_k":     50.0,
            "stochrsi_d":     50.0,
            "stochrsi_zone":  "Neutral",
            "stochrsi_cross": "Neutral",
            "cci":            0.0,
            "cci_signal":     "Neutral",
            "score":          50.0,
            "label":          "Neutral",
        },

        # ── Volatility ────────────────────────────────────────────────────
        "volatility": {
            "atr":         0.0,
            "atr_pct":     0.0,
            "atr_state":   "Stable",
            "regime":      "Moderate",
            "bb_upper":    0.0,
            "bb_middle":   0.0,
            "bb_lower":    0.0,
            "bb_width":    0.0,
            "bb_position": "N/A",
            "bb_squeeze":  False,
            "kc_upper":    0.0,
            "kc_lower":    0.0,
            "hist_vol":    0.0,
        },

        # ── Volume ────────────────────────────────────────────────────────
        "volume": {
            "current":        0.0,
            "avg_20":         0.0,
            "rvol":           1.0,
            "trend":          "Stable",
            "spike":          False,
            "buy_pressure":   50.0,
            "sell_pressure":  50.0,
            "vwap":           0.0,
            "price_vs_vwap":  "N/A",
        },

        # ── Market Health ─────────────────────────────────────────────────
        "market_health": {
            "bull_score":    0.0,
            "bear_score":    0.0,
            "neutral_score": 100.0,
            "overall_score": 0.0,
            "label":         "Weak",
        },

        # ── Multi Timeframe ───────────────────────────────────────────────
        "multi_timeframe": {
            "timeframes": {
                "5m":  "Neutral",
                "15m": "Neutral",
                "1h":  "Neutral",
                "4h":  "Neutral",
                "1D":  "Neutral",
            },
            "overall_bias":    "Neutral",
            "alignment_score": 0.0,
            "bull_count":      0,
            "bear_count":      0,
        },

        # ── AI Confidence ─────────────────────────────────────────────────
        "confidence": {
            "score":       0.0,
            "grade":       "D",
            "explanation": [],
        },

        # ── Risk Analysis ─────────────────────────────────────────────────
        "risk": {
            "score":         50.0,
            "category":      "Moderate",
            "position_size": 5.0,
            "max_risk_pct":  1.0,
            "leverage":      "1x–2x",
        },

        # ── AI Summary ────────────────────────────────────────────────────
        "summary": {
            "bias":        "Neutral",
            "strength":    "Weak",
            "probability": 0.0,
            "status":      "Wait for Better Setup",
            "highlights":  [],
        },
    }


# ── Global in-memory cache store ─────────────────────────────────────────────
_store: Dict[str, Dict[str, Any]] = {}


def get_analysis_cache(symbol: str) -> Optional[Dict[str, Any]]:
    return _store.get(symbol)


def save_analysis_cache(symbol: str, cache: Dict[str, Any]):
    _store[symbol] = cache


def clear_analysis_cache(symbol: Optional[str] = None):
    if symbol:
        _store.pop(symbol, None)
    else:
        _store.clear()
