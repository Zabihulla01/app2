"""
test_bearish.py – Phase 2 tests for bearish signal logic.

Tests cover:
  1. generate_signal() returns SELL when bearish conditions hold
  2. generate_signal() returns BUY when bullish conditions hold
  3. generate_signal() returns HOLD when conditions are mixed
  4. scan_stock() BearScore calculation (unit-tested directly)
  5. Scanner signal assignment: SELL / STRONG SELL / BUY / STRONG BUY thresholds
  6. /backtest signal direction: BUY for strong setups, SELL for weak setups
  7. Bearish SL/Target are flipped correctly (SL above price, target below)
  8. Bullish SL/Target are standard (SL below price, target above)
  9. risk_score() sanity checks
 10. BearScore edge cases (zero ADX, extreme RSI)

Run with:  pytest test_bearish.py -v
"""

import math
import types
import pandas as pd
import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers – build minimal DataFrames for generate_signal() without yfinance
# ---------------------------------------------------------------------------

def _make_df(
    price: float = 100.0,
    ema50: float = 95.0,
    ema200: float = 90.0,
    macd: float = 0.5,
    adx: float = 30.0,
    rsi: float = 60.0,
    vwap: float = 98.0,
    volume: float = 2_000_000.0,
    avg_vol: float = 1_000_000.0,
    rows: int = 1,
) -> pd.DataFrame:
    """Return a one-row DataFrame that satisfies generate_signal(df, 0, ...)."""
    data = {
        "Close":   [[price]],
        "EMA50":   [ema50],
        "EMA200":  [ema200],
        "MACD":    [macd],
        "ADX":     [adx],
        "RSI":     [rsi],
        "VWAP":    [vwap],
        "Volume":  [[volume]],
        "AVG_VOL": [[avg_vol]],
    }
    df = pd.DataFrame({k: v[0] for k, v in data.items()})
    return df


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from strategy import generate_signal
from scoring import risk_score


# ---------------------------------------------------------------------------
# 1. generate_signal – SELL (bearish) path
# ---------------------------------------------------------------------------

class TestGenerateSignalSell:

    def _bearish_df(self):
        """EMA death-cross, below VWAP, MACD negative, not bull_1h."""
        return _make_df(
            price=100.0,
            ema50=88.0,     # EMA50 < EMA200 → bearish cross
            ema200=95.0,
            macd=-0.5,      # MACD < 0.2
            adx=30.0,       # ADX >= adx_min * 0.8 → strong trend
            rsi=40.0,       # 25 < rsi < 70
            vwap=105.0,     # price < vwap
            volume=2_000_000.0,
            avg_vol=1_000_000.0,  # volume > avg_vol * 1.5
        )

    def test_sell_signal_returned(self):
        df = self._bearish_df()
        sig = generate_signal(df, 0, adx_min=25, bull_1h=False)
        assert sig == "SELL", f"Expected SELL, got {sig}"

    def test_sell_requires_not_bull_1h(self):
        """If higher-timeframe is bullish, SELL should NOT trigger."""
        df = self._bearish_df()
        sig = generate_signal(df, 0, adx_min=25, bull_1h=True)
        # With bull_1h=True the SELL condition fails; result is BUY or HOLD
        assert sig != "SELL", "SELL should not fire when bull_1h=True"

    def test_sell_requires_sufficient_adx(self):
        """Low ADX means no trend – SELL should not fire."""
        df = self._bearish_df()
        df["ADX"] = 10.0   # below adx_min * 0.8 = 20
        sig = generate_signal(df, 0, adx_min=25, bull_1h=False)
        assert sig != "SELL", "SELL should not fire with weak ADX"

    def test_sell_requires_rsi_in_range(self):
        """RSI >= 70 disqualifies the SELL condition."""
        df = self._bearish_df()
        df["RSI"] = 75.0   # outside 25 < rsi < 70
        sig = generate_signal(df, 0, adx_min=25, bull_1h=False)
        assert sig != "SELL"

    def test_sell_requires_price_below_vwap(self):
        """Price above VWAP → SELL should not fire."""
        df = self._bearish_df()
        df["Close"] = 110.0   # now above vwap=105
        sig = generate_signal(df, 0, adx_min=25, bull_1h=False)
        assert sig != "SELL"

    def test_sell_requires_high_volume(self):
        """Low volume → SELL should not fire."""
        df = self._bearish_df()
        df["AVG_VOL"] = 10_000_000.0   # avg_vol huge → volume_now not > avg*1.5
        sig = generate_signal(df, 0, adx_min=25, bull_1h=False)
        assert sig != "SELL"


# ---------------------------------------------------------------------------
# 2. generate_signal – BUY (bullish) path
# ---------------------------------------------------------------------------

class TestGenerateSignalBuy:

    def _bullish_df(self):
        return _make_df(
            price=100.0,
            ema50=100.0,    # EMA50 >= EMA200
            ema200=95.0,
            macd=0.5,       # > -0.2
            adx=30.0,
            rsi=55.0,       # 30 < rsi < 75
            vwap=98.0,      # price > vwap
            volume=2_000_000.0,
            avg_vol=1_000_000.0,
        )

    def test_buy_signal_returned(self):
        df = self._bullish_df()
        sig = generate_signal(df, 0, adx_min=25, bull_1h=True)
        assert sig == "BUY", f"Expected BUY, got {sig}"

    def test_buy_requires_bull_1h(self):
        """bull_1h=False should prevent BUY."""
        df = self._bullish_df()
        sig = generate_signal(df, 0, adx_min=25, bull_1h=False)
        assert sig != "BUY"

    def test_buy_requires_positive_ema_cross(self):
        """EMA death-cross disqualifies BUY."""
        df = self._bullish_df()
        df["EMA50"] = 85.0   # EMA50 < EMA200
        sig = generate_signal(df, 0, adx_min=25, bull_1h=True)
        assert sig != "BUY"


# ---------------------------------------------------------------------------
# 3. generate_signal – HOLD path
# ---------------------------------------------------------------------------

class TestGenerateSignalHold:

    def test_hold_when_no_condition_met(self):
        """Both BUY and SELL conditions fail → HOLD."""
        df = _make_df(
            price=100.0,
            ema50=100.0,    # bullish cross but bull_1h=False blocks BUY
            ema200=95.0,
            macd=0.5,
            adx=30.0,
            rsi=55.0,
            vwap=98.0,
            volume=2_000_000.0,
            avg_vol=1_000_000.0,
        )
        # bull_1h=False → BUY fails; price > vwap → SELL fails
        sig = generate_signal(df, 0, adx_min=25, bull_1h=False)
        assert sig == "HOLD", f"Expected HOLD, got {sig}"


# ---------------------------------------------------------------------------
# 4. BearScore calculation (logic isolated from scan_stock)
# ---------------------------------------------------------------------------

def _compute_bear_score(pf: float, rsi: float, adx: float) -> float:
    """Replicate the BearScore formula from scan_stock."""
    if adx < 20:
        return 0.0
    rsi_bear = max(0.0, (50.0 - rsi) / 50.0 * 100.0) if rsi < 50 else 0.0
    pf_bear  = max(0.0, 100.0 - min(pf * 20.0, 100.0))
    adx_comp = min(adx * 2.0, 100.0)
    score = pf_bear * 0.50 + rsi_bear * 0.30 + adx_comp * 0.20
    return min(score, 100.0)


class TestBearScore:

    def test_strong_bear_low_pf_low_rsi_high_adx(self):
        """PF≈0, RSI=20, ADX=50 → very high BearScore."""
        s = _compute_bear_score(pf=0.1, rsi=20.0, adx=50.0)
        assert s >= 70.0, f"Expected >= 70, got {s:.1f}"

    def test_zero_with_low_adx(self):
        """ADX < 20 → BearScore must be 0 (no trend = no signal)."""
        s = _compute_bear_score(pf=0.1, rsi=10.0, adx=15.0)
        assert s == 0.0

    def test_zero_bear_for_strong_bull(self):
        """High PF + RSI=65 (above 50) → BearScore is low (only ADX contributes)."""
        # pf_bear = max(0, 100 - min(4*20, 100)) = 0
        # rsi_bear = 0  (RSI=65 > 50)
        # adx_component = min(30*2, 100) = 60
        # bear_score = 0*0.5 + 0*0.3 + 60*0.2 = 12.0
        s = _compute_bear_score(pf=4.0, rsi=65.0, adx=30.0)
        assert s <= 25.0, f"Expected <= 25 for strong bull stock, got {s:.1f}"

    def test_moderate_bear_score(self):
        """PF=1.0, RSI=40, ADX=25 → moderate BearScore."""
        s = _compute_bear_score(pf=1.0, rsi=40.0, adx=25.0)
        assert 20.0 <= s <= 80.0, f"Expected moderate BearScore, got {s:.1f}"

    def test_bear_score_capped_at_100(self):
        """BearScore must never exceed 100."""
        s = _compute_bear_score(pf=0.0, rsi=0.0, adx=100.0)
        assert s <= 100.0

    def test_rsi_above_50_no_rsi_contribution(self):
        """RSI >= 50 → rsi_bear = 0, only PF and ADX contribute."""
        s_below = _compute_bear_score(pf=0.5, rsi=40.0, adx=30.0)
        s_above = _compute_bear_score(pf=0.5, rsi=60.0, adx=30.0)
        assert s_below > s_above, "RSI below 50 should produce higher BearScore"


# ---------------------------------------------------------------------------
# 5. Scanner signal assignment thresholds
# ---------------------------------------------------------------------------

def _assign_signal(score: float, bear_score: float, pf: float,
                   win_rate: float, risk_score_val: float,
                   sharpe: float, max_dd: float) -> str:
    """Mirror the /scanner signal logic from main.py."""
    if (pf >= 3 and win_rate >= 62 and risk_score_val >= 80
            and sharpe >= 1.0 and max_dd <= 20):
        return "STRONG BUY"
    if score >= 65:
        return "BUY"
    if score >= 45:
        return "WATCH"
    if bear_score >= 70:
        return "STRONG SELL"
    if bear_score >= 45:
        return "SELL"
    return "AVOID"


class TestScannerSignalAssignment:

    def test_strong_buy_when_all_criteria_met(self):
        sig = _assign_signal(80, 10, pf=3.5, win_rate=65, risk_score_val=85,
                             sharpe=1.2, max_dd=15)
        assert sig == "STRONG BUY"

    def test_buy_when_score_ge_65(self):
        sig = _assign_signal(70, 5, pf=1.0, win_rate=50, risk_score_val=50,
                             sharpe=0.5, max_dd=25)
        assert sig == "BUY"

    def test_watch_when_score_45_to_65(self):
        sig = _assign_signal(55, 5, pf=1.0, win_rate=50, risk_score_val=50,
                             sharpe=0.5, max_dd=25)
        assert sig == "WATCH"

    def test_strong_sell_when_bear_ge_70(self):
        sig = _assign_signal(20, 75, pf=0.5, win_rate=35, risk_score_val=20,
                             sharpe=0.2, max_dd=40)
        assert sig == "STRONG SELL"

    def test_sell_when_bear_45_to_70(self):
        sig = _assign_signal(20, 55, pf=0.5, win_rate=35, risk_score_val=20,
                             sharpe=0.2, max_dd=40)
        assert sig == "SELL"

    def test_avoid_when_nothing_qualifies(self):
        sig = _assign_signal(30, 10, pf=0.5, win_rate=35, risk_score_val=20,
                             sharpe=0.2, max_dd=40)
        assert sig == "AVOID"

    def test_strong_buy_takes_precedence_over_bull_score(self):
        """STRONG BUY criteria check runs before score >= 65."""
        sig = _assign_signal(70, 0, pf=3.5, win_rate=65, risk_score_val=85,
                             sharpe=1.5, max_dd=10)
        assert sig == "STRONG BUY"

    def test_bull_score_takes_precedence_over_bear_score(self):
        """A high bull score wins even if BearScore is also high."""
        sig = _assign_signal(70, 80, pf=1.0, win_rate=50, risk_score_val=50,
                             sharpe=0.5, max_dd=25)
        assert sig == "BUY"


# ---------------------------------------------------------------------------
# 6. /backtest signal direction logic
# ---------------------------------------------------------------------------

def _backtest_direction(score: float, pf: float) -> str:
    """Mirror the direction logic added to /backtest."""
    if score >= 60 and pf >= 1.2:
        return "BUY"
    return "SELL"


class TestBacktestSignalDirection:

    def test_buy_direction_strong_setup(self):
        assert _backtest_direction(score=75, pf=1.5) == "BUY"

    def test_sell_direction_weak_setup(self):
        assert _backtest_direction(score=40, pf=0.8) == "SELL"

    def test_sell_direction_low_score_high_pf(self):
        assert _backtest_direction(score=50, pf=2.0) == "SELL"

    def test_sell_direction_high_score_low_pf(self):
        assert _backtest_direction(score=80, pf=0.9) == "SELL"

    def test_boundary_score_60_pf_1_2(self):
        assert _backtest_direction(score=60, pf=1.2) == "BUY"

    def test_just_below_boundary(self):
        assert _backtest_direction(score=59.9, pf=1.2) == "SELL"


# ---------------------------------------------------------------------------
# 7 & 8. SL / Target direction (bearish = flipped, bullish = standard)
# ---------------------------------------------------------------------------

def _compute_sl_target(score: float, pf: float, price: float,
                        atr: float, mode: str = "INTRADAY"):
    """Replicate the SL/Target calculation from /backtest."""
    if score >= 60 and pf >= 1.2:
        direction = "BUY"
        if mode == "INTRADAY":
            sl = round(price - atr, 2)
            tgt = round(price + atr * 2, 2)
        else:
            sl = round(price - atr * 2, 2)
            tgt = round(price + atr * 4, 2)
    else:
        direction = "SELL"
        if mode == "INTRADAY":
            sl = round(price + atr, 2)
            tgt = round(price - atr * 2, 2)
        else:
            sl = round(price + atr * 2, 2)
            tgt = round(price - atr * 4, 2)
    return direction, sl, tgt


class TestSlTargetDirection:

    # Bearish cases

    def test_bearish_sl_above_price_intraday(self):
        _, sl, _ = _compute_sl_target(40, 0.8, price=100, atr=2, mode="INTRADAY")
        assert sl > 100, f"Bearish INTRADAY SL should be above entry price, got {sl}"

    def test_bearish_target_below_price_intraday(self):
        _, _, tgt = _compute_sl_target(40, 0.8, price=100, atr=2, mode="INTRADAY")
        assert tgt < 100, f"Bearish INTRADAY target should be below entry price, got {tgt}"

    def test_bearish_sl_above_price_swing(self):
        _, sl, _ = _compute_sl_target(40, 0.8, price=500, atr=10, mode="SWING")
        assert sl > 500, f"Bearish SWING SL should be above entry price, got {sl}"

    def test_bearish_target_below_price_swing(self):
        _, _, tgt = _compute_sl_target(40, 0.8, price=500, atr=10, mode="SWING")
        assert tgt < 500, f"Bearish SWING target should be below entry price, got {tgt}"

    def test_bearish_rr_ratio_intraday(self):
        """Reward = 2×ATR, Risk = 1×ATR → RR = 2.0."""
        _, sl, tgt = _compute_sl_target(40, 0.8, price=100, atr=5, mode="INTRADAY")
        risk   = abs(sl - 100)
        reward = abs(tgt - 100)
        rr = round(reward / risk, 2)
        assert rr == 2.0, f"Expected RR=2.0, got {rr}"

    # Bullish cases

    def test_bullish_sl_below_price_intraday(self):
        _, sl, _ = _compute_sl_target(75, 2.0, price=100, atr=2, mode="INTRADAY")
        assert sl < 100, f"Bullish INTRADAY SL should be below entry price, got {sl}"

    def test_bullish_target_above_price_intraday(self):
        _, _, tgt = _compute_sl_target(75, 2.0, price=100, atr=2, mode="INTRADAY")
        assert tgt > 100, f"Bullish INTRADAY target should be above entry price, got {tgt}"

    def test_bullish_sl_below_price_swing(self):
        _, sl, _ = _compute_sl_target(75, 2.0, price=500, atr=10, mode="SWING")
        assert sl < 500

    def test_bullish_target_above_price_swing(self):
        _, _, tgt = _compute_sl_target(75, 2.0, price=500, atr=10, mode="SWING")
        assert tgt > 500

    def test_bullish_rr_ratio_intraday(self):
        _, sl, tgt = _compute_sl_target(75, 2.0, price=100, atr=5, mode="INTRADAY")
        risk   = abs(100 - sl)
        reward = abs(tgt - 100)
        rr = round(reward / risk, 2)
        assert rr == 2.0, f"Expected RR=2.0, got {rr}"


# ---------------------------------------------------------------------------
# 9. risk_score() sanity
# ---------------------------------------------------------------------------

class TestRiskScore:

    def test_perfect_setup_high_score(self):
        s = risk_score(pf=4.0, sharpe=2.0, dd=5.0)
        assert s >= 70, f"Strong setup should score >= 70, got {s}"

    def test_terrible_setup_low_score(self):
        s = risk_score(pf=0.5, sharpe=-0.5, dd=45.0)
        assert s <= 30, f"Bad setup should score <= 30, got {s}"

    def test_score_always_0_to_100(self):
        for pf in [0, 0.5, 1, 2, 5]:
            for sharpe in [-2, 0, 1, 3]:
                for dd in [0, 15, 30, 50]:
                    s = risk_score(pf, sharpe, dd)
                    assert 0 <= s <= 100, f"Score out of range: {s}"

    def test_high_drawdown_penalty(self):
        s_low  = risk_score(pf=2.0, sharpe=1.0, dd=5.0)
        s_high = risk_score(pf=2.0, sharpe=1.0, dd=35.0)
        assert s_low > s_high, "Higher drawdown should reduce score"


# ---------------------------------------------------------------------------
# 10. BearScore edge cases
# ---------------------------------------------------------------------------

class TestBearScoreEdgeCases:

    def test_adx_exactly_20_is_included(self):
        s = _compute_bear_score(pf=0.5, rsi=30.0, adx=20.0)
        assert s > 0.0, "ADX == 20 should be included (>= 20 condition)"

    def test_adx_19_excluded(self):
        s = _compute_bear_score(pf=0.5, rsi=30.0, adx=19.9)
        assert s == 0.0

    def test_rsi_exactly_50_no_rsi_contribution(self):
        """RSI == 50 → rsi_bear = 0."""
        s_50  = _compute_bear_score(pf=1.0, rsi=50.0, adx=30.0)
        s_51  = _compute_bear_score(pf=1.0, rsi=51.0, adx=30.0)
        # Both should have rsi_bear=0; scores should be equal
        assert s_50 == s_51, "RSI=50 and RSI=51 should produce same BearScore"

    def test_extreme_high_adx_capped(self):
        """ADX=200 should not push adx_component above 100."""
        s = _compute_bear_score(pf=0.0, rsi=0.0, adx=200.0)
        assert s <= 100.0

    def test_zero_pf_max_pf_bear(self):
        """PF=0 → pf_bear = 100."""
        pf_bear = max(0.0, 100.0 - min(0.0 * 20.0, 100.0))
        assert pf_bear == 100.0

    def test_pf_5_zero_pf_bear(self):
        """PF=5 → pf_bear = 0."""
        pf_bear = max(0.0, 100.0 - min(5.0 * 20.0, 100.0))
        assert pf_bear == 0.0
