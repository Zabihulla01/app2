"""
test_scanner_reliability.py
Scanner reliability tests: missing Confidence, missing RiskScore,
empty data, and invalid ticker.
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

# ── Make backtest-service importable ────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backtest-service"))
import importlib
main = importlib.import_module("main")
scan_stock = main.scan_stock


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_backtest_result(**overrides):
    """Return a minimal valid backtest dict, overriding specified keys."""
    base = {
        "Stock":        "TEST.NS",
        "Confidence":   70,
        "RiskScore":    65,
        "WinRate":      55.0,
        "ProfitFactor": 1.8,
        "Sharpe":       1.2,
        "ADX":          30.0,
        "RSI":          45.0,
        "MaxDrawdown":  12.0,
        "Sharpe":       1.1,
    }
    base.update(overrides)
    return base


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
            result = scan_stock("TEST.NS")
        # Should not raise; result may be None or a dict
        assert result is None or isinstance(result, dict)

    def test_confidence_defaults_to_zero(self):
        """When Confidence is absent, scan result must use 0."""
        payload = _make_backtest_result(RiskScore=75)
        del payload["Confidence"]

        with patch.object(main, "backtest", return_value=payload):
            result = scan_stock("TEST.NS")

        if result is not None:
            assert result["Confidence"] == 0

    def test_scan_skipped_when_both_zero(self):
        """Returns None when both Confidence and RiskScore are missing/zero."""
        payload = _make_backtest_result()
        del payload["Confidence"]
        del payload["RiskScore"]

        with patch.object(main, "backtest", return_value=payload):
            result = scan_stock("TEST.NS")
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
            result = scan_stock("TEST.NS")
        assert result is None or isinstance(result, dict)

    def test_riskscore_defaults_to_zero(self):
        payload = _make_backtest_result(Confidence=80)
        del payload["RiskScore"]

        with patch.object(main, "backtest", return_value=payload):
            result = scan_stock("TEST.NS")

        if result is not None:
            assert result["RiskScore"] == 0

    def test_bull_score_uses_zero_riskscore(self):
        """Score should still be computable (no KeyError) with RiskScore=0."""
        payload = _make_backtest_result(Confidence=80)
        del payload["RiskScore"]

        with patch.object(main, "backtest", return_value=payload):
            result = scan_stock("TEST.NS")

        if result is not None:
            assert isinstance(result["Score"], float)
            assert 0.0 <= result["Score"] <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Empty / insufficient DataFrame  →  "No objects to concatenate" /
#    "single positional indexer is out-of-bounds"
# ─────────────────────────────────────────────────────────────────────────────

class TestEmptyData:
    """backtest() called with a stock whose yfinance download is empty."""

    def test_empty_dataframe_returns_error_dict(self):
        """
        When yfinance returns an empty DataFrame, backtest should return a
        dict with 'error' key, not raise an exception.
        """
        empty_df = pd.DataFrame()

        with patch("yfinance.download", return_value=empty_df):
            result = main.backtest("EMPTY.NS")

        assert isinstance(result, dict)
        # Must not have raised; must contain some indicator of failure
        assert "error" in result or result.get("Status") == "INVALID_STOCK"

    def test_scan_stock_survives_empty_dataframe(self):
        """scan_stock must never raise when backtest returns an error dict."""
        error_payload = {"Stock": "EMPTY.NS", "error": "No market data",
                         "Confidence": 0, "RiskScore": 0}

        with patch.object(main, "backtest", return_value=error_payload):
            result = scan_stock("EMPTY.NS")

        # Returns None (skipped) or a partial dict – but never raises
        assert result is None or isinstance(result, dict)

    def test_concat_empty_series_no_exception(self):
        """
        If all TR component series are empty, backtest should return an
        error dict, not raise ValueError('No objects to concatenate').
        """
        # Build a DataFrame with enough rows for the walk-forward split
        # but whose OHLC columns are all NaN so TR series will be empty
        idx = pd.date_range("2023-01-01", periods=300, freq="15min")
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
        df_nan.columns = pd.MultiIndex.from_tuples(
            [(c, "NANSTOCK.NS") for c in df_nan.columns]
        )

        with patch("yfinance.download", return_value=df_nan):
            try:
                result = main.backtest("NANSTOCK.NS")
                # Must return a dict, not raise
                assert isinstance(result, dict)
            except Exception as exc:
                pytest.fail(f"backtest raised unexpectedly: {exc}")

    def test_atr_rolling_empty_no_exception(self):
        """
        Fewer than 14 rows → rolling(14) returns all-NaN → iloc[-1] would
        raise.  backtest should return an error dict instead.
        """
        idx = pd.date_range("2023-01-01", periods=5, freq="15min")
        tiny_df = pd.DataFrame(
            {
                "Open":   [100.0] * 5,
                "High":   [102.0] * 5,
                "Low":    [98.0]  * 5,
                "Close":  [101.0] * 5,
                "Volume": [1_000_000] * 5,
            },
            index=idx,
        )
        tiny_df.columns = pd.MultiIndex.from_tuples(
            [(c, "TINY.NS") for c in tiny_df.columns]
        )

        with patch("yfinance.download", return_value=tiny_df):
            try:
                result = main.backtest("TINY.NS")
                assert isinstance(result, dict)
            except Exception as exc:
                pytest.fail(f"backtest raised unexpectedly: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Invalid ticker
# ─────────────────────────────────────────────────────────────────────────────

class TestInvalidTicker:
    """Ticker that yfinance doesn't recognise → empty DataFrame."""

    def test_invalid_ticker_backtest_returns_dict(self):
        """backtest('INVALIDXXX.NS') must return a dict, never raise."""
        empty_df = pd.DataFrame()

        with patch("yfinance.download", return_value=empty_df):
            result = main.backtest("INVALIDXXX.NS")

        assert isinstance(result, dict)

    def test_invalid_ticker_scan_stock_returns_none_or_partial(self):
        """scan_stock with an invalid ticker must return None or a partial dict."""
        empty_df = pd.DataFrame()

        with patch("yfinance.download", return_value=empty_df):
            result = scan_stock("INVALIDXXX.NS")

        assert result is None or isinstance(result, dict)

    def test_invalid_ticker_scan_stock_no_raise(self):
        """scan_stock must never propagate an exception for any ticker."""
        empty_df = pd.DataFrame()

        with patch("yfinance.download", return_value=empty_df):
            try:
                scan_stock("GARBAGETICKERZZZ.NS")
            except Exception as exc:
                pytest.fail(f"scan_stock raised unexpectedly: {exc}")

    def test_partial_result_has_scan_error_key_on_exception(self):
        """
        When an unexpected exception occurs inside scan_stock, the returned
        partial dict must contain a 'ScanError' key with the error message.
        """
        with patch.object(main, "backtest", side_effect=RuntimeError("network failure")):
            result = scan_stock("CRASH.NS")

        assert result is not None, "Expected partial dict, got None"
        assert "ScanError" in result
        assert "network failure" in result["ScanError"]
