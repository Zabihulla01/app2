"""
binance.py
==========
Binance public REST API — OHLCV data fetcher.

No API key required. Free, fast, no rate limit issues for public endpoints.
Used as PRIMARY source for crypto OHLCV data, replacing CoinGecko.

Binance kline intervals:
  1m 3m 5m 15m 30m 1h 2h 4h 6h 8h 12h 1d 3d 1w 1M

Internal symbol mapping:
  BTC-USD  → BTCUSDT
  ETH-USD  → ETHUSDT
  SOL-USD  → SOLUSDT
  etc.
"""

import time
import logging
import requests
import pandas as pd

logger = logging.getLogger(__name__)

BINANCE_BASE_URL = "https://api.binance.com/api/v3"
BINANCE_TIMEOUT  = 10   # seconds — fast API, no need for long timeout

# Internal symbol → Binance symbol
SYMBOL_TO_BINANCE = {
    "BTC-USD":  "BTCUSDT",
    "ETH-USD":  "ETHUSDT",
    "SOL-USD":  "SOLUSDT",
    "BNB-USD":  "BNBUSDT",
    "XRP-USD":  "XRPUSDT",
    "ADA-USD":  "ADAUSDT",
    "DOGE-USD": "DOGEUSDT",
    "AVAX-USD": "AVAXUSDT",
    "DOT-USD":  "DOTUSDT",
    "LINK-USD": "LINKUSDT",
    "MATIC-USD":"MATICUSDT",
    "ARB-USD":  "ARBUSDT",
    "LTC-USD":  "LTCUSDT",
    "TRX-USD":  "TRXUSDT",
}

# Internal timeframe → Binance interval + limit
TIMEFRAME_TO_BINANCE = {
    "1m":  {"interval": "1m",  "limit": 1000},
    "5m":  {"interval": "5m",  "limit": 1000},
    "15m": {"interval": "15m", "limit": 1000},
    "30m": {"interval": "30m", "limit": 500},
    "1h":  {"interval": "1h",  "limit": 500},
    "4h":  {"interval": "4h",  "limit": 250},
    "1d":  {"interval": "1d",  "limit": 200},
}


def _to_binance_symbol(symbol: str) -> str:
    """Convert internal symbol (BTC-USD) to Binance symbol (BTCUSDT)."""
    # Direct map first
    if symbol in SYMBOL_TO_BINANCE:
        return SYMBOL_TO_BINANCE[symbol]
    # Fallback: strip -USD and append USDT
    base = symbol.upper().replace("-USD", "").replace("-USDT", "")
    return base + "USDT"


def fetch_ohlcv_binance(symbol: str, timeframe: str = "1h") -> pd.DataFrame:
    """
    Fetch OHLCV candles from Binance public API.

    Parameters
    ----------
    symbol    : internal symbol e.g. "BTC-USD"
    timeframe : "15m" | "1h" | "4h" | "1d"

    Returns
    -------
    pd.DataFrame with columns [Open, High, Low, Close, Volume]
    UTC-aware DatetimeIndex. Empty DataFrame on failure.
    """
    cfg = TIMEFRAME_TO_BINANCE.get(timeframe, TIMEFRAME_TO_BINANCE["1h"])
    binance_sym = _to_binance_symbol(symbol)

    url = f"{BINANCE_BASE_URL}/klines"
    params = {
        "symbol":   binance_sym,
        "interval": cfg["interval"],
        "limit":    cfg["limit"],
    }

    try:
        resp = requests.get(url, params=params, timeout=BINANCE_TIMEOUT)

        if resp.status_code != 200:
            logger.warning("Binance HTTP %s for %s %s", resp.status_code, symbol, timeframe)
            return pd.DataFrame()

        data = resp.json()
        if not data or not isinstance(data, list):
            logger.warning("Binance: empty response for %s %s", symbol, timeframe)
            return pd.DataFrame()

        # Binance kline format:
        # [open_time, open, high, low, close, volume, close_time, ...]
        df = pd.DataFrame(data, columns=[
            "timestamp", "Open", "High", "Low", "Close", "Volume",
            "close_time", "quote_volume", "trades",
            "taker_base", "taker_quote", "ignore"
        ])

        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp").sort_index()
        df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)

        logger.info("Binance OHLCV OK: %s %s (%d rows)", symbol, timeframe, len(df))
        return df

    except requests.RequestException as exc:
        logger.error("Binance request error for %s %s: %s", symbol, timeframe, exc)
        return pd.DataFrame()
    except Exception as exc:
        logger.error("Binance parse error for %s %s: %s", symbol, timeframe, exc)
        return pd.DataFrame()


def fetch_live_price_binance(symbol: str) -> dict:
    """
    Fetch live price from Binance ticker endpoint.

    Returns dict: {"price": float, "change_24h": float, "high_24h": float,
                   "low_24h": float, "volume_24h": float, "source": "binance"}
    Empty dict on failure.
    """
    binance_sym = _to_binance_symbol(symbol)
    url = f"{BINANCE_BASE_URL}/ticker/24hr"
    params = {"symbol": binance_sym}

    try:
        resp = requests.get(url, params=params, timeout=BINANCE_TIMEOUT)
        if resp.status_code != 200:
            return {}
        d = resp.json()
        return {
            "price":      float(d.get("lastPrice", 0)),
            "change_24h": float(d.get("priceChangePercent", 0)),
            "high_24h":   float(d.get("highPrice", 0)),
            "low_24h":    float(d.get("lowPrice", 0)),
            "volume_24h": float(d.get("quoteVolume", 0)),  # in USDT
            "source":     "binance",
        }
    except Exception as exc:
        logger.error("Binance live price error for %s: %s", symbol, exc)
        return {}
