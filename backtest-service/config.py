# config.py — Crypto-only configuration
# All Indian stock (.NS/.BO) and US stock symbols removed.
# Primary config is crypto_config.py — this file kept for legacy imports.

STOCKS = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "BNB-USD",
    "XRP-USD",
]

SECTOR_CONFIG = {
    "BTC-USD": {
        "adx":  20,
        "hold": 8,
        "rr":   2,
    },
    "ETH-USD": {
        "adx":  20,
        "hold": 8,
        "rr":   2,
    },
    "SOL-USD": {
        "adx":  22,
        "hold": 6,
        "rr":   2,
    },
    "BNB-USD": {
        "adx":  20,
        "hold": 8,
        "rr":   2,
    },
    "XRP-USD": {
        "adx":  18,
        "hold": 6,
        "rr":   2,
    },
}

BROKERAGE       = 0.001   # 0.1% crypto exchange fee
SLIPPAGE        = 0.001   # 0.1% slippage
INITIAL_CAPITAL = 10000
RISK_PER_TRADE  = 0.01

PERIOD   = "90d"
INTERVAL = "1d"
