# walkforward_eval.py — Walk-forward back-test evaluator (crypto-only)
# yfinance removed: 1h market trend data now fetched via CoinGecko/fetch_ohlcv.

from walkforward import walkforward_split
from indicators import add_indicators
from market_filter import market_trend
from strategy import generate_signal
from risk import calculate_profit
from scoring import risk_score
from coingecko import fetch_ohlcv

import numpy as np


def evaluate(df, stock, adx_min, hold, target_rr):
    splits = walkforward_split(df)
    results = []

    for i, (train, test) in enumerate(splits):
        test = add_indicators(test)

        # ── Fetch 1h data for market trend (CoinGecko primary, yfinance fallback) ──
        try:
            df1h = fetch_ohlcv(stock, timeframe="1h")
        except Exception:
            df1h = None

        bull = market_trend(df1h["Close"].squeeze()) if (df1h is not None and not df1h.empty) else True

        wins    = 0
        losses  = 0
        gp      = 0
        gl      = 0
        returns = []

        for j in range(50, len(test) - hold):
            signal = generate_signal(test, j, adx_min, bull)

            if signal == "HOLD":
                continue

            current = float(test["Close"].iloc[j])
            future  = float(test["Close"].iloc[j + hold])

            move = (future - current) if signal == "BUY" else (current - future)

            profit = calculate_profit(
                move,
                test["ATR"].iloc[j],
                target_rr
            )

            returns.append(profit)

            if profit > 0:
                wins += 1
                gp   += profit
            else:
                losses += 1
                gl     += abs(profit)

        total = wins + losses
        pf    = (gp / gl) if gl else 0

        sharpe = (
            np.mean(returns) / np.std(returns)
            if len(returns) > 1 else 0
        )

        maxdd = 0
        if len(returns):
            cum   = np.cumsum(returns)
            peak  = np.maximum.accumulate(cum)
            maxdd = np.max(peak - cum)

        results.append({
            "Window":    i + 1,
            "Train":     len(train),
            "Test":      len(test),
            "Trades":    total,
            "PF":        round(pf,     2),
            "Sharpe":    round(sharpe, 2),
            "RiskScore": round(risk_score(pf, sharpe, maxdd), 2),
        })

    return results
