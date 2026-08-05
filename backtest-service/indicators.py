"""
indicators.py
=============
Add all technical indicators to a raw OHLCV DataFrame.
Called by both the backtest engine and Stage 1 analysis.
"""

import numpy as np
import pandas as pd
import ta


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicators. Returns the enriched DataFrame."""
    if len(df) < 20:
        return df

    close  = df["Close"].squeeze()
    high   = df["High"].squeeze()
    low    = df["Low"].squeeze()
    volume = df["Volume"].squeeze()

    # ── Moving Averages ───────────────────────────────────────────────────
    df["EMA_9"]   = close.ewm(span=9,   adjust=False).mean()
    df["EMA_21"]  = close.ewm(span=21,  adjust=False).mean()
    df["EMA_50"]  = close.ewm(span=50,  adjust=False).mean()
    df["EMA_200"] = close.ewm(span=200, adjust=False).mean()
    # Legacy aliases used by backtest engine
    df["EMA50"]   = df["EMA_50"]
    df["EMA200"]  = df["EMA_200"]

    # ── RSI ───────────────────────────────────────────────────────────────
    df["RSI"] = ta.momentum.RSIIndicator(close, window=14).rsi()

    # ── Stochastic RSI ────────────────────────────────────────────────────
    try:
        srsi = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
        df["StochRSI_K"] = srsi.stochrsi_k() * 100
        df["StochRSI_D"] = srsi.stochrsi_d() * 100
    except Exception:
        df["StochRSI_K"] = np.nan
        df["StochRSI_D"] = np.nan

    # ── CCI ───────────────────────────────────────────────────────────────
    try:
        df["CCI"] = ta.trend.CCIIndicator(high, low, close, window=20).cci()
    except Exception:
        df["CCI"] = np.nan

    # ── MACD ──────────────────────────────────────────────────────────────
    macd_ind = ta.trend.MACD(close)
    df["MACD"]        = macd_ind.macd()
    df["MACD_Signal"] = macd_ind.macd_signal()
    df["MACD_Hist"]   = macd_ind.macd_diff()

    # ── ADX + DI ──────────────────────────────────────────────────────────
    adx_ind = ta.trend.ADXIndicator(high, low, close, window=14)
    df["ADX"]    = adx_ind.adx()
    df["+DI"]    = adx_ind.adx_pos()
    df["-DI"]    = adx_ind.adx_neg()

    # ── ATR ───────────────────────────────────────────────────────────────
    df["ATR"] = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()

    # ── Bollinger Bands ───────────────────────────────────────────────────
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    df["BB_Upper"]  = bb.bollinger_hband()
    df["BB_Middle"] = bb.bollinger_mavg()
    df["BB_Lower"]  = bb.bollinger_lband()
    df["BB_Width"]  = (df["BB_Upper"] - df["BB_Lower"]) / df["BB_Middle"] * 100

    # ── Keltner Channels ──────────────────────────────────────────────────
    try:
        kc = ta.volatility.KeltnerChannel(high, low, close, window=20, window_atr=10)
        df["KC_Upper"]  = kc.keltner_channel_hband()
        df["KC_Middle"] = kc.keltner_channel_mband()
        df["KC_Lower"]  = kc.keltner_channel_lband()
    except Exception:
        df["KC_Upper"]  = np.nan
        df["KC_Middle"] = np.nan
        df["KC_Lower"]  = np.nan

    # ── Supertrend ────────────────────────────────────────────────────────
    df["Supertrend"], df["Supertrend_Dir"] = _supertrend(high, low, close, period=10, multiplier=3.0)

    # ── VWAP (cumulative session) ─────────────────────────────────────────
    df["VWAP"] = (close * volume).cumsum() / volume.cumsum()

    # ── Volume ────────────────────────────────────────────────────────────
    df["AVG_VOL"] = volume.rolling(20).mean()
    df["RVOL"]    = volume / df["AVG_VOL"]   # Relative Volume

    # ── Support / Resistance ──────────────────────────────────────────────
    df["SUPPORT"]    = low.rolling(20).min()
    df["RESISTANCE"] = high.rolling(20).max()

    return df


def _supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 10, multiplier: float = 3.0):
    """
    Calculate Supertrend indicator.
    Returns (supertrend_line, direction) where direction: 1=bullish, -1=bearish
    """
    hl2   = (high + low) / 2
    atr   = ta.volatility.AverageTrueRange(high, low, close, window=period).average_true_range()

    upper_basic = hl2 + (multiplier * atr)
    lower_basic = hl2 - (multiplier * atr)

    upper_band = upper_basic.copy()
    lower_band = lower_basic.copy()

    for i in range(1, len(close)):
        upper_band.iloc[i] = (
            upper_basic.iloc[i]
            if upper_basic.iloc[i] < upper_band.iloc[i-1] or close.iloc[i-1] > upper_band.iloc[i-1]
            else upper_band.iloc[i-1]
        )
        lower_band.iloc[i] = (
            lower_basic.iloc[i]
            if lower_basic.iloc[i] > lower_band.iloc[i-1] or close.iloc[i-1] < lower_band.iloc[i-1]
            else lower_band.iloc[i-1]
        )

    supertrend = pd.Series(index=close.index, dtype=float)
    direction  = pd.Series(index=close.index, dtype=int)

    for i in range(1, len(close)):
        if close.iloc[i] > upper_band.iloc[i-1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < lower_band.iloc[i-1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i-1] if i > 0 else 1

        supertrend.iloc[i] = lower_band.iloc[i] if direction.iloc[i] == 1 else upper_band.iloc[i]

    return supertrend, direction
