"""
test_scanner_reliability.py
Scanner reliability tests (crypto-only).
All Indian stock (.NS/.BO) and yfinance.download references removed.
Data fetching is now handled by coingecko.fetch_ohlcv — mocked here.
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

# ── Make backtest-service importable ─────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backtest-service"))
import importlib
main = importlib.import_module("main")
scan_stock = main.scan_stock


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_backtest_result(**overrides):
    """Return a minimal valid backtest dict for a crypto symbol."""
    base = {
        "Stock":        "BTC-USD",
        "Confidence":   70,
        "RiskScore":    65,
        "WinRate":      55.0,
        "ProfitFactor": 1.8,
        "Sharpe":       1.2,
        "ADX":          30.0,
        "RSI":          45.0,
        "MaxDrawdown":  12.0,
        "EntryPrice":   63000.0,
        "ATR":          300.0,
        "Signal":       "BUY",
    }
    base.update(overrides)
    return base


def _make_ohlcv_df(rows=300, price=63000.0):
    """Build a minimal OHLCV DataFrame that fetch_ohlcv would return."""
    idx = pd.date_range("2024-01-01", periods=rows, freq="1h")
    return pd.DataFrame(
        {
            "Open":   price * 0.999,
            "High":   price * 1.002,
            "Low":    price * 0.997,
            "Close":  price,
            "Volume": 1_000_000,
        },
        index=idx,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Missing Confidence key
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingConfidence:
    """backtest() returns a dict without 'Confidence' (e.g. error path)."""

    def test_no_keyerror_when_confidence_missing(self):
        """scan_stock must not raise KeyError when Confidence is absent."""
        payload = _make_backtest_result()
        del payload["Confidence"]

        with patch.object(main, "backtest", return_value=payload):
            result = scan_stock("BTC-USD")
        assert result is None or isinstance(result, dict)

    def test_confidence_defaults_to_zero(self):
        """When Confidence is absent, scan result must use 0."""
        payload = _make_backtest_result(RiskScore=75)
        del payload["Confidence"]

        with patch.object(main, "backtest", return_value=payload):
            result = scan_stock("BTC-USD")

        if result is not None:
            assert result["Confidence"] == 0

    def test_scan_skipped_when_both_zero(self):
        """Returns None when both Confidence and RiskScore are missing/zero."""
        payload = _make_backtest_result()
        del payload["Confidence"]
        del payload["RiskScore"]

        with patch.object(main, "backtest", return_value=payload):
            result = scan_stock("BTC-USD")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Missing RiskScore key
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingRiskScore:
    """backtest() returns a dict without 'RiskScore'."""

    def test_no_keyerror_when_riskscore_missing(self):
        payload = _make_backtest_result()
        del payload["RiskScore"]

        with patch.object(main, "backtest", return_value=payload):
            result = scan_stock("ETH-USD")
        assert result is None or isinstance(result, dict)

    def test_riskscore_defaults_to_zero(self):
        payload = _make_backtest_result(Stock="ETH-USD", Confidence=80)
        del payload["RiskScore"]

        with patch.object(main, "backtest", return_value=payload):
            result = scan_stock("ETH-USD")

        if result is not None:
            assert result["RiskScore"] == 0

    def test_bull_score_uses_zero_riskscore(self):
        """Score should still be computable (no KeyError) with RiskScore=0."""
        payload = _make_backtest_result(Stock="ETH-USD", Confidence=80)
        del payload["RiskScore"]

        with patch.object(main, "backtest", return_value=payload):
            result = scan_stock("ETH-USD")

        if result is not None:
            assert isinstance(result["Score"], float)
            assert 0.0 <= result["Score"] <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Empty / insufficient OHLCV data from CoinGecko
# ─────────────────────────────────────────────────────────────────────────────

class TestEmptyData:
    """backtest() called when fetch_ohlcv returns empty DataFrame."""

    def test_empty_dataframe_returns_error_dict(self):
        """
        When fetch_ohlcv returns an empty DataFrame, backtest should return
        a dict with 'error' key — not raise an exception.
        """
        empty_df = pd.DataFrame()

        with patch("coingecko.fetch_ohlcv", return_value=empty_df):
            result = main.backtest("BTC-USD")

        assert isinstance(result, dict)
        assert "error" in result or result.get("Status") == "INVALID_STOCK"

    def test_scan_stock_survives_empty_dataframe(self):
        """scan_stock must never raise when backtest returns an error dict."""
        error_payload = {
            "Stock":      "SOL-USD",
            "error":      "No market data",
            "Confidence": 0,
            "RiskScore":  0,
        }

        with patch.object(main, "backtest", return_value=error_payload):
            result = scan_stock("SOL-USD")

        assert result is None or isinstance(result, dict)

    def test_all_nan_ohlcv_no_exception(self):
        """
        All-NaN OHLCV should produce an error dict, not raise ValueError.
        """
        idx = pd.date_range("2024-01-01", periods=300, freq="1h")
        df_nan = pd.DataFrame(
            {
                "Open":   np.nan,
                "High":   np.nan,
                "Low":    np.nan,
                "Close":  np.nan,
                "Volume": 0,
            },
            index=idx,
        )

        with patch("coingecko.fetch_ohlcv", return_value=df_nan):
            try:
                result = main.backtest("BNB-USD")
                assert isinstance(result, dict)
            except Exception as exc:
                pytest.fail(f"backtest raised unexpectedly: {exc}")

    def test_too_few_rows_no_exception(self):
        """
        Fewer than 14 rows → rolling(14) all-NaN → backtest should return
        an error dict, not raise IndexError.
        """
        idx = pd.date_range("2024-01-01", periods=5, freq="1h")
        tiny_df = pd.DataFrame(
            {
                "Open":   [63000.0] * 5,
                "High":   [63200.0] * 5,
                "Low":    [62800.0] * 5,
                "Close":  [63100.0] * 5,
                "Volume": [1_000_000] * 5,
            },
            index=idx,
        )

        with patch("coingecko.fetch_ohlcv", return_value=tiny_df):
            try:
                result = main.backtest("XRP-USD")
                assert isinstance(result, dict)
            except Exception as exc:
                pytest.fail(f"backtest raised unexpectedly: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Invalid / unknown crypto ticker
# ─────────────────────────────────────────────────────────────────────────────

class TestInvalidTicker:
    """CoinGecko returns empty data for unknown tickers."""

    def test_invalid_ticker_backtest_returns_dict(self):
        """backtest('INVALID-USD') must return a dict, never raise."""
        empty_df = pd.DataFrame()

        with patch("coingecko.fetch_ohlcv", return_value=empty_df):
            result = main.backtest("INVALID-USD")

        assert isinstance(result, dict)

    def test_invalid_ticker_scan_stock_returns_none_or_partial(self):
        """scan_stock with an unknown ticker must return None or a partial dict."""
        empty_df = pd.DataFrame()

        with patch("coingecko.fetch_ohlcv", return_value=empty_df):
            result = scan_stock("INVALID-USD")

        assert result is None or isinstance(result, dict)

    def test_invalid_ticker_scan_stock_no_raise(self):
        """scan_stock must never propagate an exception for any ticker."""
        empty_df = pd.DataFrame()

        with patch("coingecko.fetch_ohlcv", return_value=empty_df):
            try:
                scan_stock("GARBAGETICKER-USD")
            except Exception as exc:
                pytest.fail(f"scan_stock raised unexpectedly: {exc}")

    def test_partial_result_has_scan_error_key_on_exception(self):
        """
        When an unexpected exception occurs inside scan_stock, the returned
        partial dict must contain a 'ScanError' key with the error message.
        """
        with patch.object(main, "backtest", side_effect=RuntimeError("network failure")):
            result = scan_stock("CRASH-USD")

        assert result is not None, "Expected partial dict, got None"
        assert "ScanError" in result
        assert "network failure" in result["ScanError"]
