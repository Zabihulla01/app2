"""
coingecko.py
============
CoinGecko data fetcher for the Crypto AI Trading System.

Architecture:
  - CoinGecko free API  → primary source for 1h / 1d OHLCV and live prices
  - yfinance            → fallback for 15m data (not available on CoinGecko
                          free tier) and as a general backup when CoinGecko
                          rate-limits or fails

Public API surface
------------------
  fetch_ohlcv(symbol, timeframe)   → pd.DataFrame  (OHLCV, DatetimeIndex)
  fetch_live_price(coingecko_id)   → dict           (price, change_24h, …)
  fetch_live_prices(coin_ids)      → dict[id → dict]
"""

import time
import logging
import requests
import pandas as pd
import numpy as np
import yfinance as yf

from crypto_config import (
    COINGECKO_BASE_URL,
    COINGECKO_TIMEOUT,
    COINGECKO_RATE_WAIT,
    SYMBOL_TO_COINGECKO,
    TIMEFRAME_CONFIG,
    BACKTEST_PERIOD,
)

logger = logging.getLogger(__name__)

# ── Internal rate-limit tracker ───────────────────────────────────────────────
_last_cg_request: float = 0.0


def _cg_get(path, params=None):
    """
    Perform a CoinGecko GET request with automatic rate-limit spacing.
    Returns parsed JSON on success, None on any error.
    """
    global _last_cg_request

    # Enforce minimum spacing between requests (free tier: 30 req/min)
    elapsed = time.time() - _last_cg_request
    if elapsed < COINGECKO_RATE_WAIT:
        time.sleep(COINGECKO_RATE_WAIT - elapsed)

    url = f"{COINGECKO_BASE_URL}/{path.lstrip('/')}"
    try:
        resp = requests.get(url, params=params or {}, timeout=COINGECKO_TIMEOUT)
        _last_cg_request = time.time()

        if resp.status_code == 429:
            logger.warning("CoinGecko rate-limited (429). Sleeping 60s.")
            time.sleep(60)
            return None

        if resp.status_code != 200:
            logger.warning("CoinGecko HTTP %s for %s", resp.status_code, url)
            return None

        return resp.json()

    except requests.RequestException as exc:
        logger.error("CoinGecko request error: %s", exc)
        return None


# ── OHLCV helpers ─────────────────────────────────────────────────────────────

def _cg_ohlcv(coingecko_id: str, days: int) -> pd.DataFrame:
    """
    Fetch OHLCV candles from CoinGecko /coins/{id}/ohlc endpoint.
    Returns DataFrame with columns [Open, High, Low, Close, Volume] or empty.

    Note: /ohlc does not include volume; Volume is set to 0 and then
    enriched from market_chart if needed.  Callers that need accurate volume
    should use _cg_market_chart instead.
    """
    data = _cg_get(
        f"coins/{coingecko_id}/ohlc",
        params={"vs_currency": "usd", "days": str(days)},
    )
    if not data or not isinstance(data, list) or len(data) == 0:
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=["timestamp", "Open", "High", "Low", "Close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index()
    df["Volume"] = 0.0   # OHLC endpoint has no volume
    return df.astype(float)


def _cg_market_chart(coingecko_id: str, days: int, interval: str) -> pd.DataFrame:
    """
    Fetch price + volume from CoinGecko /coins/{id}/market_chart.
    interval: "daily" or "hourly"

    Returns DataFrame with columns [Close, Volume] indexed by UTC datetime.
    No OHLC — use alongside _cg_ohlcv or yfinance for full OHLCV.
    """
    data = _cg_get(
        f"coins/{coingecko_id}/market_chart",
        params={"vs_currency": "usd", "days": str(days), "interval": interval},
    )
    if not data:
        return pd.DataFrame()

    prices  = data.get("prices", [])
    volumes = data.get("total_volumes", [])

    if not prices:
        return pd.DataFrame()

    price_df  = pd.DataFrame(prices,  columns=["timestamp", "Close"])
    volume_df = pd.DataFrame(volumes, columns=["timestamp", "Volume"])

    df = price_df.merge(volume_df, on="timestamp", how="left")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index()
    return df.astype(float)


def _build_ohlcv_from_chart(coingecko_id: str, days: int, interval: str) -> pd.DataFrame:
    """
    Merge OHLC candles with volume from market_chart to produce a full OHLCV
    DataFrame.  Aligns on the nearest timestamp via merge_asof.
    """
    ohlc   = _cg_ohlcv(coingecko_id, days)
    chart  = _cg_market_chart(coingecko_id, days, interval)

    if ohlc.empty:
        return pd.DataFrame()

    if not chart.empty:
        # merge_asof requires sorted DatetimeIndex → reset/merge/re-index
        ohlc_r  = ohlc.reset_index()
        chart_r = chart[["Volume"]].reset_index()
        merged  = pd.merge_asof(
            ohlc_r.sort_values("timestamp"),
            chart_r.sort_values("timestamp"),
            on="timestamp",
            direction="nearest",
            tolerance=pd.Timedelta("2h"),
        )
        merged = merged.set_index("timestamp").sort_index()
        # Use chart volume; fallback to 0 already in ohlc
        if "Volume_y" in merged.columns:
            merged["Volume"] = merged["Volume_y"].fillna(0)
            merged = merged.drop(columns=["Volume_x", "Volume_y"], errors="ignore")
        df = merged
    else:
        df = ohlc

    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)


def _yf_ohlcv(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """
    Fetch OHLCV from yfinance.  Flattens MultiIndex columns automatically.
    Returns empty DataFrame on failure.
    """
    try:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        # Flatten MultiIndex columns (yfinance ≥0.2.x)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty:
            return pd.DataFrame()

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index, utc=True)
        return df.astype(float)

    except Exception as exc:
        logger.error("yfinance error for %s [%s %s]: %s", symbol, period, interval, exc)
        return pd.DataFrame()


def _resample_to_4h(df: pd.DataFrame) -> pd.DataFrame:
    """Resample a 1h DataFrame to 4h OHLCV candles."""
    if df.empty:
        return df
    return df.resample("4h").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna()


# ── Public: fetch OHLCV ───────────────────────────────────────────────────────

# ── Public: fetch OHLCV ───────────────────────────────────────────────────────

def fetch_ohlcv(symbol, timeframe="1h"):
    """
    Fetch OHLCV data for a crypto symbol.

    Data source priority:
      1. Binance REST API  — primary (fast, no rate limit)
      2. CoinGecko         — fallback if Binance returns insufficient data
      3. yfinance          — last resort fallback

    Parameters
    ----------
    symbol    : yfinance/internal symbol, e.g. "BTC-USD"
    timeframe : "15m" | "1h" | "4h" | "1d"

    Returns
    -------
    pd.DataFrame with columns [Open, High, Low, Close, Volume]
    and a UTC-aware DatetimeIndex.  Empty DataFrame on failure.
    """
    from binance import fetch_ohlcv_binance

    # ── 1. Binance primary (fast, no rate limit) ──────────────────────────
    df = fetch_ohlcv_binance(symbol, timeframe)
    if not df.empty and len(df) >= 30:
        return df

    logger.warning("Binance returned %d rows for %s %s — trying CoinGecko", len(df), symbol, timeframe)

    # ── 2. CoinGecko fallback ─────────────────────────────────────────────
    cfg    = TIMEFRAME_CONFIG.get(timeframe, TIMEFRAME_CONFIG["1h"])
    source = cfg["source"]
    cg_id  = SYMBOL_TO_COINGECKO.get(symbol)

    if source == "coingecko" and cg_id:
        days     = cfg.get("days", 90)
        interval = cfg.get("interval", "hourly")
        df_cg = _build_ohlcv_from_chart(cg_id, days, interval)
        if not df_cg.empty and len(df_cg) >= 30:
            logger.info("CoinGecko fallback OK: %s %s (%d rows)", symbol, timeframe, len(df_cg))
            return df_cg

    # ── 3. yfinance last resort ───────────────────────────────────────────
    logger.warning("CoinGecko insufficient for %s %s — falling back to yfinance", symbol, timeframe)

    if timeframe == "4h":
        df_1h = _yf_ohlcv(symbol, "60d", "1h")
        if not df_1h.empty:
            return _resample_to_4h(df_1h)

    yf_interval = {"1d": "1d", "1h": "1h", "15m": "15m"}.get(timeframe, "1h")
    yf_period   = "60d" if timeframe == "15m" else BACKTEST_PERIOD
    return _yf_ohlcv(symbol, yf_period, yf_interval)


# ── Public: live price data ───────────────────────────────────────────────────

def fetch_live_price(coingecko_id):
    """
    Fetch live price, 24h change, volume, and market cap for one coin.

    Returns dict:
      {
        "price":       float,
        "change_24h":  float,   # percent
        "volume_24h":  float,   # USD
        "market_cap":  float,   # USD
        "high_24h":    float,
        "low_24h":     float,
        "last_updated": str,
      }
    Returns empty dict on failure.
    """
    data = _cg_get(
        "coins/markets",
        params={
            "vs_currency":           "usd",
            "ids":                   coingecko_id,
            "order":                 "market_cap_desc",
            "per_page":              1,
            "page":                  1,
            "sparkline":             "false",
            "price_change_percentage": "24h",
        },
    )
    if not data or not isinstance(data, list) or len(data) == 0:
        logger.warning("fetch_live_price: no data for %s", coingecko_id)
        return {}

    coin = data[0]
    return {
        "price":        coin.get("current_price",                    0.0),
        "change_24h":   coin.get("price_change_percentage_24h",      0.0),
        "volume_24h":   coin.get("total_volume",                     0.0),
        "market_cap":   coin.get("market_cap",                       0.0),
        "high_24h":     coin.get("high_24h",                         0.0),
        "low_24h":      coin.get("low_24h",                          0.0),
        "last_updated": coin.get("last_updated",                     ""),
    }


def fetch_live_prices(coin_ids):
    """
    Fetch live data for multiple coins in a single API request.

    Parameters
    ----------
    coin_ids : list of CoinGecko IDs, e.g. ["bitcoin", "ethereum"]

    Returns
    -------
    dict mapping CoinGecko ID → live price dict (same shape as fetch_live_price)
    """
    if not coin_ids:
        return {}

    ids_str = ",".join(coin_ids)
    data = _cg_get(
        "coins/markets",
        params={
            "vs_currency":             "usd",
            "ids":                     ids_str,
            "order":                   "market_cap_desc",
            "per_page":                50,
            "page":                    1,
            "sparkline":               "false",
            "price_change_percentage": "24h",
        },
    )
    if not data or not isinstance(data, list):
        logger.warning("fetch_live_prices: empty response for %s", ids_str)
        return {}

    result = {}
    for coin in data:
        cg_id = coin.get("id", "")
        result[cg_id] = {
            "price":        coin.get("current_price",                    0.0),
            "change_24h":   coin.get("price_change_percentage_24h",      0.0),
            "volume_24h":   coin.get("total_volume",                     0.0),
            "market_cap":   coin.get("market_cap",                       0.0),
            "high_24h":     coin.get("high_24h",                         0.0),
            "low_24h":      coin.get("low_24h",                          0.0),
            "last_updated": coin.get("last_updated",                     ""),
            "name":         coin.get("name",                             ""),
            "symbol":       coin.get("symbol",                           "").upper(),
        }
    return result
