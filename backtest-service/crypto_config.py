"""
crypto_config.py
================
Single configuration file for the Crypto AI Trading System.

To add a new cryptocurrency later:
  1. Add an entry to CRYPTO_COINS list.
  2. Add its trading parameters to CRYPTO_SECTOR_CONFIG.
  3. Restart the backtest service — no other code changes needed.

CoinGecko ID reference: https://api.coingecko.com/api/v3/coins/list
yfinance symbol format: BTC-USD, ETH-USD, SOL-USD, etc.
"""

# ── Supported coins ───────────────────────────────────────────────────────────
# Each entry maps the yfinance/display symbol to the CoinGecko coin ID.
# yfinance_symbol : used for historical OHLCV (backtest, 1d/1h/15m)
# coingecko_id    : used for live price, market cap, 24h change, volume
# ─────────────────────────────────────────────────────────────────────────────
CRYPTO_COINS = [
    {
        "symbol":          "BTC-USD",      # yfinance / display symbol
        "coingecko_id":    "bitcoin",       # CoinGecko coin ID
        "name":            "Bitcoin",
        "short":           "BTC",
    },
    {
        "symbol":          "ETH-USD",
        "coingecko_id":    "ethereum",
        "name":            "Ethereum",
        "short":           "ETH",
    },
    # ── Add more coins here ──────────────────────────────────────────────
    # {
    #     "symbol":       "SOL-USD",
    #     "coingecko_id": "solana",
    #     "name":         "Solana",
    #     "short":        "SOL",
    # },
    # {
    #     "symbol":       "BNB-USD",
    #     "coingecko_id": "binancecoin",
    #     "name":         "BNB",
    #     "short":        "BNB",
    # },
]

# Convenience: list of yfinance symbols used by the scanner
SCAN_SYMBOLS = [c["symbol"] for c in CRYPTO_COINS]

# Convenience: map symbol -> coingecko_id
SYMBOL_TO_COINGECKO = {c["symbol"]: c["coingecko_id"] for c in CRYPTO_COINS}

# Convenience: map symbol -> display name
SYMBOL_TO_NAME = {c["symbol"]: c["name"] for c in CRYPTO_COINS}

# ── Per-coin backtest parameters ──────────────────────────────────────────────
# adx  : minimum ADX value required for signal (crypto is more volatile → lower)
# hold : candles to hold trade after entry
# rr   : risk/reward ratio for target calculation
# ─────────────────────────────────────────────────────────────────────────────
CRYPTO_SECTOR_CONFIG = {
    "BTC-USD": {"adx": 20, "hold": 12, "rr": 2.0},
    "ETH-USD": {"adx": 20, "hold": 12, "rr": 2.0},
    # "SOL-USD": {"adx": 18, "hold": 10, "rr": 2.5},
    # "BNB-USD": {"adx": 20, "hold": 12, "rr": 2.0},
}

# Default parameters for any coin not listed above
DEFAULT_CRYPTO_CONFIG = {"adx": 20, "hold": 12, "rr": 2.0}

# ── Data fetch settings ───────────────────────────────────────────────────────
# Timeframes available via CoinGecko free tier:
#   "1d"  → /coins/{id}/market_chart  (days=90, interval=daily)
#   "1h"  → /coins/{id}/market_chart  (days=90, interval=hourly)
#   "15m" → NOT available on CoinGecko free tier
#              → fallback to yfinance (period=60d, interval=15m)
# ─────────────────────────────────────────────────────────────────────────────
TIMEFRAME_CONFIG = {
    "1d":  {"source": "coingecko", "days": 90,  "interval": "daily"},
    "1h":  {"source": "coingecko", "days": 90,  "interval": "hourly"},
    "4h":  {"source": "yfinance",  "period": "60d", "interval": "1h"},   # resample 1h→4h
    "15m": {"source": "yfinance",  "period": "60d", "interval": "15m"},
}

# Default timeframes used by backtest and scanner
BACKTEST_INTERVAL  = "1h"    # primary backtest timeframe
BACKTEST_PERIOD    = "90d"   # yfinance period string (used as fallback)
TREND_INTERVAL     = "1d"    # higher-timeframe trend confirmation

# ── Capital / risk settings ───────────────────────────────────────────────────
INITIAL_CAPITAL = 10_000   # USD
RISK_PER_TRADE  = 0.01     # 1 % of capital per trade
SLIPPAGE        = 0.001    # 0.1 % slippage per trade
BROKERAGE       = 0        # crypto exchanges use % fees via SLIPPAGE

# ── Scanner cache ─────────────────────────────────────────────────────────────
SCANNER_CACHE_SECONDS = 300   # 5 minutes

# ── CoinGecko API ─────────────────────────────────────────────────────────────
COINGECKO_BASE_URL  = "https://api.coingecko.com/api/v3"
COINGECKO_TIMEOUT   = 15      # seconds
COINGECKO_RATE_WAIT = 1.5     # seconds between requests (free tier: 30 req/min)

# ── Currency display ──────────────────────────────────────────────────────────
CURRENCY_SYMBOL = "$"
CURRENCY_CODE   = "USD"

# ── Binance WebSocket stream mapping ─────────────────────────────────────────
# Maps Binance miniTicker stream name → internal symbol (yfinance format).
# Used by _binance_ws_task() in main.py.
# Binance uses USDT pairs which are equivalent to USD for display purposes.
# Free public data — no API key required.
# ─────────────────────────────────────────────────────────────────────────────
BINANCE_STREAM_MAP = {
    "btcusdt":  "BTC-USD",
    "ethusdt":  "ETH-USD",
    "solusdt":  "SOL-USD",
    "bnbusdt":  "BNB-USD",
    "xrpusdt":  "XRP-USD",
    "adausdt":  "ADA-USD",
    "dogeusdt": "DOGE-USD",
    "avaxusdt": "AVAX-USD",
    "dotusdt":  "DOT-USD",
    "linkusdt": "LINK-USD",
}
