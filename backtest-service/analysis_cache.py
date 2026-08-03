"""
Analysis Cache Module
----------------------
Stores all technical analysis results from Stage 1.
Stage 2 (Decision Engine) reads ONLY from this cache.
"""

from datetime import datetime
from typing import Dict, Any, Optional
import json


class AnalysisCache:
    """
    Structured cache for all technical analysis results.
    Stage 1 populates this. Stage 2 reads from it.
    """
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
    
    def create(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        Create a new cache structure for a symbol.
        Returns the cache dict that Stage 1 will populate.
        """
        cache = {
            # ── Metadata ──────────────────────────────────────────────
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            
            # ── Price Action ──────────────────────────────────────────
            "current_price": 0.0,
            "atr": 0.0,
            "volatility": 0.0,
            
            # ── Trend Analysis ────────────────────────────────────────
            "trend": None,                    # "BULLISH" | "BEARISH" | "NEUTRAL"
            "trend_strength": 0.0,            # 0-100
            "market_structure": None,         # "UPTREND" | "DOWNTREND" | "RANGING"
            "structure_break": False,         # True if structure broken
            
            # ── Support & Resistance ──────────────────────────────────
            "support": 0.0,
            "resistance": 0.0,
            "support_strength": 0.0,
            "resistance_strength": 0.0,
            
            # ── Volume Analysis ───────────────────────────────────────
            "volume_analysis": {
                "current_volume": 0.0,
                "avg_volume": 0.0,
                "volume_trend": None,         # "INCREASING" | "DECREASING" | "STABLE"
                "volume_spike": False,
            },
            
            # ── Liquidity Analysis ────────────────────────────────────
            "liquidity_analysis": {
                "liquidity_score": 0.0,       # 0-100
                "spread": 0.0,
                "depth": None,                # "HIGH" | "MEDIUM" | "LOW"
            },
            
            # ── Volatility Analysis ───────────────────────────────────
            "volatility_analysis": {
                "atr_percentile": 0.0,        # ATR vs 14-day average
                "volatility_regime": None,    # "HIGH" | "MEDIUM" | "LOW"
                "bollinger_width": 0.0,
            },
            
            # ── Technical Indicators ──────────────────────────────────
            "rsi_analysis": {
                "rsi": 0.0,
                "signal": None,               # "OVERBOUGHT" | "OVERSOLD" | "NEUTRAL"
                "divergence": False,
            },
            
            "macd_analysis": {
                "macd": 0.0,
                "signal": 0.0,
                "histogram": 0.0,
                "trend": None,                # "BULLISH" | "BEARISH" | "NEUTRAL"
                "crossover": False,
            },
            
            "ema_analysis": {
                "ema_9": 0.0,
                "ema_21": 0.0,
                "ema_50": 0.0,
                "ema_200": 0.0,
                "alignment": None,            # "BULLISH" | "BEARISH" | "MIXED"
                "golden_cross": False,
                "death_cross": False,
            },
            
            "atr_analysis": {
                "atr": 0.0,
                "atr_multiple": 0.0,
                "volatility_state": None,     # "EXPANDING" | "CONTRACTING" | "STABLE"
            },
            
            "bollinger_analysis": {
                "upper_band": 0.0,
                "middle_band": 0.0,
                "lower_band": 0.0,
                "bandwidth": 0.0,
                "position": None,             # "UPPER" | "MIDDLE" | "LOWER"
                "squeeze": False,
            },
            
            "adx_analysis": {
                "adx": 0.0,
                "plus_di": 0.0,
                "minus_di": 0.0,
                "trend_strength": None,       # "STRONG" | "WEAK" | "ABSENT"
            },
            
            # ── Market Health ─────────────────────────────────────────
            "market_health": {
                "overall_score": 0.0,         # 0-100
                "trend_quality": 0.0,
                "momentum_quality": 0.0,
                "volume_quality": 0.0,
            },
            
            # ── Scoring ───────────────────────────────────────────────
            "confidence_score": 0.0,          # 0-100
            "risk_score": 0.0,                # 0-100
            
            # ── Multi-Timeframe Confirmation ──────────────────────────
            "multi_timeframe_confirmation": {
                "higher_tf_trend": None,      # From 1h or 4h
                "alignment": False,           # Does current TF align with higher TF?
                "confirmation_strength": 0.0,
            },
            
            # ── Sentiment (if available) ──────────────────────────────
            "fear_greed": None,               # 0-100 or None
            
            # ── AI Summary ────────────────────────────────────────────
            "ai_summary": {
                "bias": None,                 # "BULLISH" | "BEARISH" | "NEUTRAL"
                "key_factors": [],            # List of key factors
                "warnings": [],               # List of warnings
                "opportunities": [],          # List of opportunities
            },
            
            # ── Backtest Metrics ──────────────────────────────────────
            "backtest_metrics": {
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "total_trades": 0,
                "net_profit": 0.0,
            },
        }
        
        self.data[symbol] = cache
        return cache
    
    def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached analysis for a symbol."""
        return self.data.get(symbol)
    
    def exists(self, symbol: str) -> bool:
        """Check if analysis exists for a symbol."""
        return symbol in self.data
    
    def clear(self, symbol: Optional[str] = None):
        """Clear cache for a specific symbol or all symbols."""
        if symbol:
            self.data.pop(symbol, None)
        else:
            self.data.clear()
    
    def export_json(self, symbol: str) -> str:
        """Export cache to JSON string."""
        cache = self.get(symbol)
        if not cache:
            return "{}"
        return json.dumps(cache, indent=2)
    
    def to_dict(self, symbol: str) -> Dict[str, Any]:
        """Return cache as dictionary."""
        return self.get(symbol) or {}


# ── Global cache instance ────────────────────────────────────────────────────
_global_cache = AnalysisCache()


def get_cache() -> AnalysisCache:
    """Get the global analysis cache instance."""
    return _global_cache


def create_analysis_cache(symbol: str, timeframe: str) -> Dict[str, Any]:
    """
    Create and return a new analysis cache for a symbol.
    Stage 1 uses this to initialize the cache.
    """
    return _global_cache.create(symbol, timeframe)


def get_analysis_cache(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the analysis cache for a symbol.
    Stage 2 uses this to read the analysis results.
    """
    return _global_cache.get(symbol)


def clear_analysis_cache(symbol: Optional[str] = None):
    """Clear the analysis cache."""
    _global_cache.clear(symbol)
