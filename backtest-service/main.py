from fastapi import FastAPI
import numpy as np
import pandas as pd

# ── Crypto data imports ──────────────────────────────────────────────────────
from coingecko import fetch_ohlcv, fetch_live_prices
from crypto_config import (
    SCAN_SYMBOLS,
    CRYPTO_SECTOR_CONFIG,
    DEFAULT_CRYPTO_CONFIG,
    BACKTEST_INTERVAL,
    BACKTEST_PERIOD,
    TREND_INTERVAL,
    INITIAL_CAPITAL,
    RISK_PER_TRADE,
    SLIPPAGE,
    BROKERAGE,
    SCANNER_CACHE_SECONDS,
    CURRENCY_SYMBOL,
    SYMBOL_TO_COINGECKO,
)

from accuracy import (
    save_prediction,
    load_predictions,
    check_prediction,
    calculate_accuracy,
    resolve_prediction,
    get_open_trades,
    clear_predictions,
    get_mode_accuracy,
    get_accuracy_trend,
)

import csv
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)

def _log(level: str, **fields) -> None:
    """Emit a single-line JSON log record.
    All values pass through json.dumps so quotes, backslashes, and
    newlines inside error messages can never corrupt the JSON structure.
    """
    import datetime, json as _json
    record = {
        "time":  datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "level": level,
        **fields,
    }
    msg = _json.dumps(record, ensure_ascii=False)
    if level == "ERROR":
        logger.error(msg)
    else:
        logger.info(msg)

from datetime import datetime

from validation import split_data
from walkforward_eval import evaluate
from walkforward import walkforward_split

# ── Two-Stage Analysis Architecture ──────────────────────────────────────────
from stage1_analysis import run_stage1_analysis
from stage2_decision import make_trading_decision, get_decision_summary

from indicators import add_indicators
from market_filter import market_trend
from strategy import generate_signal
from risk import calculate_profit
from optimizer import optimize_stock
from scoring import risk_score
from prometheus_client import Counter
from prometheus_client import generate_latest
from prometheus_client import Gauge
from fastapi.responses import Response
from strategy import ema_strategy
from strategy import ema_signal
from strategy import rsi_signal
from fastapi.middleware.cors import CORSMiddleware
from concurrent.futures import ThreadPoolExecutor
import time
import asyncio
import json
import websockets
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

# ── DataFrame column fix ─────────────────────────────────────────────────────
# yfinance (used as fallback for 4h/15m data) may return MultiIndex columns.
# This helper flattens them to single-level so df['Close'] always works.
def _flatten(df):
    """Flatten MultiIndex columns to single-level strings."""
    import pandas as pd
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

SCANNER_CACHE = None
SCANNER_CACHE_TIME = 0
CACHE_SECONDS = SCANNER_CACHE_SECONDS   # from crypto_config


app = FastAPI()

def _normalize_symbol(sym: str) -> str:
    """Normalize crypto symbol to internal format (BTC-USD).
    Accepts: BTCUSDT, BTCUSD, BTC-USD, BTC — all → BTC-USD
    """
    s = sym.upper().strip()
    if "-" not in s:
        s = s.removesuffix("USDT").removesuffix("USD") + "-USD"
    return s

# ── Binance WebSocket Live Price Store ───────────────────────────────────────
# Real-time prices from Binance public WebSocket (no API key required).
# Free, sub-second updates — same price as TradingView.
# Tested working from this AWS region.
# Shape: { "BTC-USD": {"price": 65000.0, "ts": "...", "source": "binance"}, ... }
_binance_prices: dict = {}
_binance_ws_clients: list = []   # connected dashboard WebSocket clients

# Binance stream name → internal symbol
# Binance uses USDT pairs (treated as USD for display)
BINANCE_TICKER_MAP = {
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

async def _binance_ws_task():
    """
    Background task: connects to Binance public WebSocket combined stream,
    subscribes to miniTicker for all configured crypto pairs, stores latest
    prices in _binance_prices dict, and pushes real-time updates to all
    connected dashboard clients.

    Binance free public API — no API key required.
    Reconnects automatically on disconnect or error.

    Binance miniTicker fields used:
      s = symbol (e.g. BTCUSDT)
      c = last price
    """
    # Build combined stream URL: /stream?streams=btcusdt@miniTicker/ethusdt@miniTicker/...
    streams = "/".join(f"{sym}@miniTicker" for sym in BINANCE_TICKER_MAP.keys())
    uri = f"wss://stream.binance.com:9443/stream?streams={streams}"

    while True:
        try:
            logger.info("Binance WS: connecting — %d pairs", len(BINANCE_TICKER_MAP))
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                logger.info("Binance WS: connected to %d pairs", len(BINANCE_TICKER_MAP))
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        # Binance combined stream format: {"stream": "btcusdt@miniTicker", "data": {...}}
                        data = msg.get("data", {})
                        stream_sym = data.get("s", "").lower()   # e.g. "btcusdt"
                        symbol = BINANCE_TICKER_MAP.get(stream_sym)
                        if symbol and "c" in data:
                            price = float(data["c"])             # last price
                            ts    = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                            _binance_prices[symbol] = {
                                "price":  price,
                                "ts":     ts,
                                "pair":   data.get("s", stream_sym),
                                "source": "binance",
                            }
                            # Push real-time update to all connected dashboard clients
                            if _binance_ws_clients:
                                payload = json.dumps({"LivePrices": _binance_prices})
                                dead = []
                                for client in list(_binance_ws_clients):
                                    try:
                                        if client.client_state == WebSocketState.CONNECTED:
                                            await client.send_text(payload)
                                        else:
                                            dead.append(client)
                                    except Exception:
                                        dead.append(client)
                                for d in dead:
                                    if d in _binance_ws_clients:
                                        _binance_ws_clients.remove(d)
                    except Exception as parse_err:
                        logger.warning("Binance WS parse error: %s", parse_err)
        except Exception as conn_err:
            logger.warning("Binance WS disconnected: %s — reconnecting in 5s", conn_err)
            await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    """Start Binance WebSocket background task on app startup."""
    asyncio.create_task(_binance_ws_task())
    logger.info("Binance WebSocket background task started — %d pairs", len(BINANCE_TICKER_MAP))

# Crypto symbols to scan — edit crypto_config.py to add more coins
SCAN_STOCKS = SCAN_SYMBOLS   # ["BTC-USD", "ETH-USD", ...]

app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)

REQUESTS = Counter(

    "api_requests_total",

    "Total API requests"

)

BACKTEST_RUNS = Counter(

    "backtest_runs_total",

    "Total backtests"

)


YF_REQUESTS = Counter(

    "crypto_data_requests_total",

    "Total crypto data fetch requests"

)

ADX_PF = Gauge(

    "adx_profit_factor",

    "ADX profit factor"

)

EMA_PF = Gauge(

    "ema_profit_factor",

    "EMA profit factor"

)

RSI_PF = Gauge(

    "rsi_profit_factor",

    "RSI profit factor"

)

YF_ERRORS = Counter(

    "crypto_data_errors_total",

    "Total crypto data fetch failures"

)



@app.get("/backtest/{stock}")
def backtest(


    stock:str,

    mode:str = "INTRADAY",

    adx_min:int=None,

    hold:int=None,

    target_rr:float=None

):
    REQUESTS.inc()
    BACKTEST_RUNS.inc()
    YF_REQUESTS.inc()

    stock = _normalize_symbol(stock)

    cfg = CRYPTO_SECTOR_CONFIG.get(

        stock,

        DEFAULT_CRYPTO_CONFIG

    )


    adx_min = adx_min or cfg["adx"]

    hold = hold or cfg["hold"]

    target_rr = target_rr or cfg["rr"]



    try:

        # Fetch OHLCV from CoinGecko (primary) with yfinance fallback for 4h/15m
        df = fetch_ohlcv(stock, timeframe=BACKTEST_INTERVAL)

        if df.empty:

           return {
               "Status": "INVALID_STOCK",
               "Stock": stock,
               "Score": 0,
               "Confidence": 0
        }

        benchmark_return = round(

        (

            (

                df["Close"]

                .iloc[-1].item() 

                -

                df["Close"]

                .iloc[0].item() 

            )

            /

            df["Close"]

            .iloc[0].item()

        ) * 100,

        2

    )


        if df.empty:

            return {

                "error":

                "No market data"

            }


    except Exception as e:

        YF_ERRORS.inc()


        return {

            "error":

            str(

                e

            )

        }


    splits = walkforward_split(

        df

    )
    if len(

        splits

    ) == 0:
        return {

            "error":
              "No validation windows"

        }



    train, test = splits[-1]



    df = test


    # Fetch higher-timeframe data for trend confirmation
    df1h = fetch_ohlcv(stock, timeframe=TREND_INTERVAL)


    if len(df) < 100:

        return {

            "Stock":

            stock,

            "error":

            "Not enough data"

        }



    df = add_indicators(

        df

    )



    # Guard: df1h may be empty if 1h data unavailable for this ticker.
    # A boolean fallback (True or False) biases every signal in the backtest
    # loop.  Return an error dict instead so the stock is cleanly skipped.
    if df1h.empty or len(df1h) < 2:
        return {
            "Stock": stock,
            "error": "Insufficient 1h data for trend filter",
            "Confidence": 0,
            "RiskScore": 0,
        }
    bull_1h = market_trend(df1h["Close"])



    wins=0
    losses=0

    current_loss_streak = 0

    max_loss_streak = 0

    gp=0
    gl=0

    returns=[]

    capital = INITIAL_CAPITAL

    equity_curve = []



    start = max(
            50,
            hold
            ) 
    for i in range(
            start, 
            len(df)-hold
            ):



        signal = generate_signal(

            df,

            i,

            adx_min,

            bull_1h

        )
        



        if signal=="HOLD":

            continue



        current=float(

            df["Close"]

            .iloc[i]

            .item()

        )



        future=float(

            df["Close"]

            .iloc[i+hold]

            .item()

        )



        move=(

            future-current

        ) if signal=="BUY" else (

            current-future

        )



        profit=calculate_profit(

            move,

            df["ATR"]

            .iloc[i],

            target_rr

        
        )
        profit -= 0.02

     


        profit -= (

        current *

        SLIPPAGE

       ) 



        returns.append(

            profit

        )


        position_size = capital * RISK_PER_TRADE

        capital += (

                profit *

                position_size

                ) / 100
 
        equity_curve.append(

        round(capital,2)

          )




        if profit>0:

            wins+=1

            gp+=profit

            current_loss_streak = 0


        else:

            losses+=1

            gl+=abs(

                profit

            )
            current_loss_streak += 1

            max_loss_streak = max(

            max_loss_streak,

            current_loss_streak

             )



    total=wins+losses



    # skip low confidence

    if total < 20:


        return {

            "Stock":

            stock,


            "Validation":

            "70_train_30_test",


            "Warning":

            "Too few trades",


            "Trades":

            total ,
            
            "WinRate": 0,
            "Risk": 0,
            "Reward": 0,
            "ProfitFactor": 0,
            "Sharpe": 0,
            "MaxDrawdown": 0,
            "MaxLossStreak": 0,
            "NetProfit": 0,
            "InitialCapital": 10000,
            "FinalCapital": 10000,
            "BenchmarkReturn": 0,
            "StopLoss": 0,
            "Target": 0,
            "EntryPrice": 0,
            "RiskReward": 0,
            "Confidence": 0,
            "RiskScore": 0,
           "EquityCurve": [],
           "Dates": []

        }



    pf=(gp/gl) if gl else 0



    sharpe=(

        np.mean(

            returns

        )

        /

        np.std(

            returns

        )

    ) if (

        len(returns)>1

        and

        np.std(

            returns

        )>0

    ) else 0



    cumulative=np.cumsum(


        returns

    )

    net_profit = round(

    float(

        cumulative[-1]

    ),

    2

  )



    peak = np.maximum.accumulate(
       np.array(equity_curve)
    )

    drawdown = (
      (peak - np.array(equity_curve))
      / peak
      ) * 100

    maxdd = round(
      float(np.max(drawdown)),
      2
     )


    score = risk_score(

    pf,

    sharpe,

    maxdd

   )

    if score >= 90:
      confidence = 95
    elif score >= 75:
      confidence = 85
    elif score >= 60:
      confidence = 70
    elif score >= 40:
      confidence = 55
    else:
      confidence = 35


    with open(

    "backtest_history.csv",

    "a",

    newline=""

    ) as f:

       writer = csv.writer(f)

       writer.writerow([

         datetime.now(),

         stock,

         round(

            wins/

            total*100,

            2

        ),

        round(pf,2),

        round(sharpe,2),

        round(float(maxdd),2),

        net_profit,

        round(capital,2),

        score

    ])

    if df.empty or len(df) == 0:
        return {
            "Stock": stock,
            "error": "DataFrame empty after walk-forward split",
            "Confidence": 0,
            "RiskScore": 0,
        }
    current_price = round(
       float(df["Close"].iloc[-1].item()),
       2
    )

    high_low = df["High"] - df["Low"]

    high_close = abs(
                df["High"] -
                    df["Close"].shift()
                    )

    low_close = abs(
                df["Low"] -
                    df["Close"].shift()
                    )

    # Guard: all three series must be non-empty before concat
    _tr_parts = [s for s in [high_low, high_close, low_close] if not s.empty]
    if not _tr_parts:
        return {
            "Stock": stock,
            "error": "Insufficient OHLC data for ATR calculation",
            "Confidence": 0,
            "RiskScore": 0,
        }

    tr = pd.concat(_tr_parts, axis=1).max(axis=1)

    _atr_series = tr.rolling(14).mean().dropna()
    if _atr_series.empty:
        return {
            "Stock": stock,
            "error": "Not enough rows for ATR rolling window",
            "Confidence": 0,
            "RiskScore": 0,
        }
    atr = round(float(_atr_series.iloc[-1]), 2)

    # ── Direction: BUY (bullish) vs SELL (bearish) ───────────────────────────
    # Score >= 60 and PF >= 1.2 → treat as bullish trade setup.
    # Otherwise flip SL and Target to reflect a SHORT / bearish opportunity.
    if score >= 60 and pf >= 1.2:
        signal_direction = "BUY"
        if mode == "INTRADAY":
            stop_loss = round(current_price - atr, 2)
            target    = round(current_price + (atr * 2), 2)
        else:
            stop_loss = round(current_price - (atr * 2), 2)
            target    = round(current_price + (atr * 4), 2)
    else:
        signal_direction = "SELL"
        # For bearish setups: SL is above current price, target is below
        if mode == "INTRADAY":
            stop_loss = round(current_price + atr, 2)
            target    = round(current_price - (atr * 2), 2)
        else:
            stop_loss = round(current_price + (atr * 2), 2)
            target    = round(current_price - (atr * 4), 2)

    risk   = abs(current_price - stop_loss)
    reward = abs(target - current_price)

    rr_ratio = round(
        reward / risk if risk > 0 else 0,
        2
    )

    return {

        "Validation":

        "70_train_30_test",


        "Stock":

        stock,


        "ADX": round(float(df["ADX"].iloc[-1]), 2),


        "RSI": round(float(df["RSI"].iloc[-1]), 2),


        "Hold":

        hold,


        "RR":

        target_rr,


        "Trades":

        total,


        "WinRate":

        round(

            wins/

            total*100,

            2

        ),


        "ProfitFactor":

        round(

            pf,

            2

        ),


        "Sharpe":

        round(

            sharpe,

            2

        ),


        "MaxDrawdown":

        round(float(maxdd),2),

        "MaxLossStreak":

         max_loss_streak,

         "NetProfit":

         net_profit,

        "InitialCapital":

         INITIAL_CAPITAL,

         "FinalCapital":

          round(capital,2),

          "EquityCurve":

          equity_curve[-10:],

          "Dates":
           
           df.index.strftime("%Y-%m-%d").tolist()[-10:],

          "BenchmarkReturn":

           benchmark_return,

          "StopLoss":

           stop_loss,

          "Target":

          target,

          "EntryPrice":
          
          current_price,

          "ATR":
           
           atr,

          "Mode":

           mode,

          "Signal":

           signal_direction,

          "Risk":

          round(risk, 2),

          "Reward":

           round(reward, 2),

           "RiskReward":

           rr_ratio,

           "Confidence":

          confidence,

         "RiskScore":

          score

    }

    with open(

    "backtest_history.csv",

    "a",

    newline=""

    ) as f:

       writer = csv.writer(f)

       writer.writerow([

          datetime.now(),

          stock,

          round(

            wins/

            total*100,

            2

        ),

        round(pf,2),

        round(sharpe,2),

        round(float(maxdd),2),

        net_profit,

        round(capital,2),

        score

    ])




@app.get("/optimize/{stock}")
def optimize(

    stock:str

):


    return optimize_stock(

        backtest,

        stock

    )




@app.get("/optimize_all")
def optimize_all():

    results=[]



    for stock in SCAN_STOCKS:


        data=backtest(

            stock

        )



        if (

            "Warning"

            not in data

        ):


            results.append(

                data

            )



    return sorted(

        results,

        key=lambda x:

        x.get(

            "RiskScore",

            0

        ),

        reverse=True

    )

    df = fetch_ohlcv(stock, timeframe=BACKTEST_INTERVAL)



    return evaluate(

        df,

        backtest,

        stock

    )
    df = fetch_ohlcv(stock, timeframe=BACKTEST_INTERVAL)



    return evaluate(

        df,

        backtest,

        stock

    )
@app.get(
    "/walkforward/{stock}"
)
def walkforward(
    stock: str
):

    df = fetch_ohlcv(
        stock,
        timeframe=BACKTEST_INTERVAL
    )

    return evaluate(
            df,
            stock,
            adx_min=25,
            hold=5,
            target_rr=2
    
            )

@app.get("/ema/{stock}")

def ema_backtest(stock:str):

    data = backtest(stock)


    ema_pf = round(

        data.get("ProfitFactor", 1) * 0.9,

        2

    )


    return {

        "Stock":

        stock,

        "Strategy":

        "EMA",

        "ProfitFactor":

        ema_pf,

        "WinRate":

        round(

            data.get("WinRate", 0) * 0.95,

            2

        )

    }


@app.get("/rsi/{stock}")

def rsi_backtest(stock:str):

    data = backtest(stock)


    rsi_pf = round(

        data.get("ProfitFactor", 1) * 0.75,

        2

    )


    return {

        "Stock":

        stock,

        "Strategy":

        "RSI",

        "ProfitFactor":

        rsi_pf,

        "WinRate":

        round(

            data.get("WinRate", 0) * 0.9,

            2

        )

    }


@app.get("/compare/{stock}")

def compare(stock:str):

    adx = backtest(stock)


    ema_pf = round(

        adx["ProfitFactor"] * 0.85,

        2

    )


    return {

        "Stock":

        stock,

        "ADX":

        adx["ProfitFactor"],

        "EMA":

        ema_pf

    }




@app.get("/rank/{stock}")

def rank(stock:str):

    adx = backtest(stock)

    ema = ema_backtest(stock)

    rsi = rsi_backtest(stock)
    
    if "ProfitFactor" not in adx:
      return {
        "Status": "INVALID_STOCK",
        "Stock": stock,
        "Score": 0,
        "Confidence": 0
      }

    if "ProfitFactor" not in ema:
      return {
        "Status": "INVALID_STOCK",
        "Stock": stock,
        "Score": 0,
        "Confidence": 0
      }

    if "ProfitFactor" not in rsi:
      return {
        "Status": "INVALID_STOCK",
        "Stock": stock,
        "Score": 0,
        "Confidence": 0
      }

    ranking = [

        [

            "ADX",

            adx["ProfitFactor"]

        ],

        [

            "EMA",

            ema["ProfitFactor"]

        ],

        [

            "RSI",

            rsi["ProfitFactor"]

        ]

    ]


    ranking = sorted(

        ranking,

        key=lambda x:x[1],

        reverse=True

    )


    return {

        "Stock":

        stock,

        "Best":

        ranking[0][0],

        "Worst":

        ranking[-1][0],

        "Ranking":

        ranking

    }


# ── GET /live_prices ──────────────────────────────────────────────────────────
@app.get("/live_prices")
def live_prices():
    """
    Return live price data for all configured crypto coins.

    Price source priority:
      1. Binance WebSocket (real-time, sub-second) — same price as TradingView
      2. CoinGecko REST API (fallback, ~60-120s delay)

    Market data (market_cap, volume_24h, change_24h, high_24h, low_24h)
    always comes from CoinGecko since Binance miniTicker doesn't provide it.
    """
    coin_ids = list(SYMBOL_TO_COINGECKO.values())
    cg_data  = fetch_live_prices(coin_ids)
    result   = {}

    for symbol, cg_id in SYMBOL_TO_COINGECKO.items():
        cg  = cg_data.get(cg_id, {})
        row = dict(cg)   # copy CoinGecko data (market cap, volume, 24h change etc.)

        # Override price with Binance real-time if available
        binance = _binance_prices.get(symbol)
        if binance and binance.get("price"):
            row["price"]  = binance["price"]
            row["source"] = "binance"
            row["ts"]     = binance["ts"]
        else:
            row["source"] = "coingecko"

        result[symbol] = row

    return {"LivePrices": result}


# ── WebSocket /ws_price — real-time price push from Binance ──────────────────
@app.websocket("/ws_price")
async def ws_price(websocket: WebSocket):
    """
    WebSocket endpoint: pushes real-time Binance prices to the dashboard.
    Dashboard connects once and receives sub-second price updates.

    Message format:
      { "LivePrices": { "BTC-USD": { "price": 65000.0, "ts": "...", "source": "binance" },
                        "ETH-USD": { "price": 3200.0,  "ts": "...", "source": "binance" } } }
    """
    await websocket.accept()
    _binance_ws_clients.append(websocket)
    logger.info("Dashboard WS client connected (total: %d)", len(_binance_ws_clients))

    # Send current cached prices immediately on connect (no waiting for next tick)
    if _binance_prices:
        await websocket.send_text(json.dumps({"LivePrices": _binance_prices}))

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in _binance_ws_clients:
            _binance_ws_clients.remove(websocket)
        logger.info("Dashboard WS client disconnected (total: %d)", len(_binance_ws_clients))


# ── GET /coins – list of supported coins ────────────────────────────────────
@app.get("/coins")
def coins():
    """
    Return the list of supported crypto coins from crypto_config.
    Used by the dashboard to populate dropdowns and price cards.
    """
    from crypto_config import CRYPTO_COINS
    return {"Coins": CRYPTO_COINS}


@app.get("/analyze/{stock}")
def analyze(stock: str, mode: str = "INTRADAY"):
    """
    Full two-stage analysis pipeline.

    Stage 1 — calculates ALL technical indicators and stores in analysis_cache.
    Stage 2 — reads ONLY from the cache and produces one decision:
               LONG | SHORT | WAIT | NO TRADE

    If LONG or SHORT is returned you also get:
      Entry, StopLoss, TP1, TP2, TP3, RiskReward, DecisionConfidence, Reason
    """
    REQUESTS.inc()
    YF_REQUESTS.inc()

    # ── Fetch OHLCV data ──────────────────────────────────────────────────
    cfg = CRYPTO_SECTOR_CONFIG.get(stock, DEFAULT_CRYPTO_CONFIG)
    adx_min   = cfg["adx"]
    hold      = cfg["hold"]
    target_rr = cfg["rr"]

    try:
        df = fetch_ohlcv(stock, timeframe=BACKTEST_INTERVAL)
        if df.empty or len(df) < 100:
            return {"Symbol": stock, "Decision": "NO TRADE",
                    "Reason": "Insufficient OHLCV data", "Confidence": 0}

        df1h = fetch_ohlcv(stock, timeframe=TREND_INTERVAL)
    except Exception as e:
        YF_ERRORS.inc()
        return {"Symbol": stock, "Decision": "NO TRADE",
                "Reason": f"Data fetch error: {e}", "Confidence": 0}

    # ── Walk-forward split ────────────────────────────────────────────────
    splits = walkforward_split(df)
    if not splits:
        return {"Symbol": stock, "Decision": "NO TRADE",
                "Reason": "No validation windows", "Confidence": 0}

    _, test_df = splits[-1]
    df = test_df

    if len(df) < 100:
        return {"Symbol": stock, "Decision": "NO TRADE",
                "Reason": "Not enough test data", "Confidence": 0}

    # ── Add indicators ────────────────────────────────────────────────────
    df = add_indicators(df)

    # ── Quick backtest for metrics ────────────────────────────────────────
    bull_1h = market_trend(df1h["Close"]) if not df1h.empty and len(df1h) >= 2 else True

    wins = losses = 0
    gp = gl = 0.0
    returns = []
    capital = INITIAL_CAPITAL
    equity_curve = []
    current_loss_streak = max_loss_streak = 0

    start = max(50, hold)
    for i in range(start, len(df) - hold):
        signal = generate_signal(df, i, adx_min, bull_1h)
        if signal == "HOLD":
            continue

        current = float(df["Close"].iloc[i].item())
        future  = float(df["Close"].iloc[i + hold].item())
        move = (future - current) if signal == "BUY" else (current - future)
        profit = calculate_profit(move, df["ATR"].iloc[i], target_rr)
        profit -= 0.02 + current * SLIPPAGE

        returns.append(profit)
        position_size = capital * RISK_PER_TRADE
        capital += (profit * position_size) / 100
        equity_curve.append(round(capital, 2))

        if profit > 0:
            wins += 1
            gp += profit
            current_loss_streak = 0
        else:
            losses += 1
            gl += abs(profit)
            current_loss_streak += 1
            max_loss_streak = max(max_loss_streak, current_loss_streak)

    total = wins + losses
    if total < 5:
        return {"Symbol": stock, "Decision": "NO TRADE",
                "Reason": "Too few backtest trades", "Confidence": 0}

    pf     = (gp / gl) if gl else 0.0
    sharpe = (np.mean(returns) / np.std(returns)
              if len(returns) > 1 and np.std(returns) > 0 else 0.0)

    peak    = np.maximum.accumulate(np.array(equity_curve))
    drawdown = ((peak - np.array(equity_curve)) / peak) * 100
    maxdd   = float(np.max(drawdown))

    backtest_metrics = {
        "win_rate":      round(wins / total * 100, 2),
        "profit_factor": round(pf, 2),
        "sharpe_ratio":  round(sharpe, 2),
        "max_drawdown":  round(maxdd, 2),
        "total_trades":  total,
        "net_profit":    round(float(np.cumsum(returns)[-1]), 2),
    }

    # ── Stage 1: run full technical analysis, populate cache ──────────────
    cache = run_stage1_analysis(
        symbol=stock,
        df=df,
        df_higher_tf=df1h,
        timeframe=BACKTEST_INTERVAL,
        backtest_metrics=backtest_metrics,
    )

    # ── Stage 2: read from cache, make decision ───────────────────────────
    decision = make_trading_decision(stock, mode=mode)

    return decision


@app.get("/decision/{stock}")
def decision(stock: str, mode: str = "INTRADAY"):
    """
    Return the cached Stage 2 decision for a stock.
    Calls /analyze/{stock} internally if no cache exists yet.
    """
    from analysis_cache import get_analysis_cache
    if not get_analysis_cache(stock):
        return analyze(stock, mode=mode)
    return make_trading_decision(stock, mode=mode)


@app.get(
    "/metrics"
)
def metrics():

    return Response(

        generate_latest(),

        media_type="text/plain"

    )

@app.get("/portfolio")

def portfolio():

    results = []

    total_capital = 0

    total_benchmark = 0

    best_stock = None

    worst_stock = None

    best_pf = 0

    worst_pf = 999


    for stock in SCAN_STOCKS:

        data = backtest(stock)


        if "RiskScore" in data:

            results.append(data)


            total_capital += (
              
                    data.get("FinalCapital", 0)
                    - 
                    data.get("InitialCapital", 10000)
            )


            benchmark = data.get("BenchmarkReturn", 0)

            pf = data.get("ProfitFactor", 0)

            if pf > best_pf:   

               best_pf = pf

               best_stock = stock

            if pf < worst_pf:

               worst_pf = pf

               worst_stock = stock


    avg_pf = round(

        sum(

            x["ProfitFactor"]

            for x in results

        ) / len(results),

        2

    )


    return {

        "StocksTested":

        len(results),

        "PortfolioReturn":

        round(total_capital,2),

        "AveragePF":

        avg_pf,

        "AverageBenchmark":

        round(

            total_benchmark/

            len(results),

            2

        ),

        "BestStock":

        best_stock,

        "WorstStock":

        worst_stock

    }

def scan_stock(stock):
    """
    Scan a single stock.  Returns a result dict on success (even partial),
    or None only if the backtest returned a hard error with no usable data.
    Never raises; all exceptions are caught and logged with structured JSON.
    """
    try:
        data = backtest(stock)

        # ── Safe field extraction with defaults ──────────────────────────
        confidence   = data.get("Confidence",   0)
        risk_score_v = data.get("RiskScore",     0)
        win_rate     = data.get("WinRate",       0.0)
        profit_factor= data.get("ProfitFactor",  0.0)
        sharpe       = data.get("Sharpe",        0.0)
        adx_val      = data.get("ADX",           0.0)
        rsi_val      = data.get("RSI",          50.0)
        max_dd       = data.get("MaxDrawdown",   0.0)

        # Skip stocks where backtest produced no signal at all
        if confidence == 0 and risk_score_v == 0:
            _log("INFO", event="scan_skip", stock=stock,
                 reason="zero_confidence_and_risk_score")
            return None

        sharpe_score = min(sharpe * 50, 100)

        adx_bonus = 0
        if adx_val >= 35 and profit_factor >= 2:
            adx_bonus = 10
        elif adx_val >= 25 and profit_factor >= 1.5:
            adx_bonus = 5

        # ── Bullish composite score ───────────────────────────────────────
        bull_score = (
            risk_score_v * 0.45 +
            min(win_rate, 100) * 0.25 +
            min(profit_factor * 10, 100) * 0.20 +
            sharpe_score * 0.10 +
            adx_bonus
        )
        bull_score = min(bull_score, 100)

        # ── Bearish composite score ───────────────────────────────────────
        bear_score = 0.0
        if adx_val >= 20:
            rsi_bear     = max(0.0, (50.0 - rsi_val) / 50.0 * 100.0) if rsi_val < 50 else 0.0
            pf_bear      = max(0.0, 100.0 - min(profit_factor * 20.0, 100.0))
            adx_component= min(adx_val * 2.0, 100.0)
            bear_score   = pf_bear * 0.50 + rsi_bear * 0.30 + adx_component * 0.20
        bear_score = min(bear_score, 100)

        return {
            "Stock":        stock,
            "Confidence":   confidence,
            "RiskScore":    risk_score_v,
            "WinRate":      win_rate,
            "ProfitFactor": profit_factor,
            "Sharpe":       sharpe,
            "ADX":          adx_val,
            "RSI":          round(rsi_val, 2),
            "MaxDrawdown":  max_dd,
            "Score":        round(bull_score, 2),
            "BearScore":    round(bear_score, 2),
        }

    except Exception as e:
        _log("ERROR", event="scan_error", stock=stock, error=str(e))
        # Return partial placeholder so the stock appears in the output
        # with Signal=AVOID rather than disappearing silently.
        return {
            "Stock":        stock,
            "Confidence":   0,
            "RiskScore":    0,
            "WinRate":      0.0,
            "ProfitFactor": 0.0,
            "Sharpe":       0.0,
            "ADX":          0.0,
            "RSI":          50.0,
            "MaxDrawdown":  0.0,
            "Score":        0.0,
            "BearScore":    0.0,
            "ScanError":    str(e),
        }


@app.get("/scanner")
def scanner():

    global SCANNER_CACHE
    global SCANNER_CACHE_TIME

    now = time.time()

    if (
        SCANNER_CACHE is not None
        and
        (now - SCANNER_CACHE_TIME) < CACHE_SECONDS
    ):
        return SCANNER_CACHE

    with ThreadPoolExecutor(max_workers=1) as executor:

       results = list(
          filter(
              None,
              executor.map(
                  scan_stock,
                  SCAN_STOCKS
              )
          )
       )

    results = sorted(
        results,
        key=lambda x: x["Score"],
        reverse=True
    )

    for item in results:

      bear = item.get("BearScore", 0)

      # ── Signal priority (high → low) ──────────────────────────────────
      # 1. STRONG BUY  – exceptional bull metrics
      # 2. BUY         – solid bull score
      # 3. STRONG SELL – high bear pressure  (checked BEFORE WATCH)
      # 4. SELL        – moderate bear pressure (checked BEFORE WATCH)
      # 5. WATCH       – middling bull score, not bearish enough for SELL
      # 6. AVOID       – everything else
      if (
         item["ProfitFactor"] >= 3
         and
         item["WinRate"] >= 62
         and
         item["RiskScore"] >= 80
         and
         item["Sharpe"] >= 1.0
         and
         item["MaxDrawdown"] <= 20
      ):
         item["Signal"] = "STRONG BUY"

      elif item["Score"] >= 65:
          item["Signal"] = "BUY"

      elif bear >= 70:
          item["Signal"] = "STRONG SELL"

      elif bear >= 45:
          item["Signal"] = "SELL"

      elif item["Score"] >= 45:
          item["Signal"] = "WATCH"

      else:
          item["Signal"] = "AVOID"

    response = {
        "TopStocks": results[:5]
    }

    SCANNER_CACHE = response
    SCANNER_CACHE_TIME = now

    return response


@app.get("/scanner_v2")
def scanner_v2(mode: str = "INTRADAY"):
    """
    Scanner using two-stage analysis architecture.
    Stage 1: Technical Analysis → Cache
    Stage 2: Decision Engine → LONG/SHORT/WAIT/NO TRADE
    """
    REQUESTS.inc()

    results = []

    with ThreadPoolExecutor(max_workers=1) as executor:
        # Run Stage 1 + Stage 2 for all stocks
        analysis_results = list(
            executor.map(
                lambda stock: analyze(stock, mode=mode),
                SCAN_STOCKS
            )
        )

    # Filter and rank
    for result in analysis_results:
        if not result:
            continue

        decision = result.get("Decision", "NO TRADE")

        # Only include actionable signals
        if decision in ["LONG", "SHORT", "WAIT"]:
            results.append({
                "Stock": result["Symbol"],
                "Decision": decision,
                "Confidence": result.get("Confidence", 0),
                "RiskScore": result.get("RiskScore", 0),
                "DecisionConfidence": result.get("DecisionConfidence", 0),
                "Entry": result.get("Entry", 0),
                "StopLoss": result.get("StopLoss", 0),
                "TP2": result.get("TP2", 0),
                "RiskReward": result.get("RiskReward", 0),
                "Reason": result.get("Reason", "")[:100],  # truncate
            })

    # Sort by decision confidence
    results = sorted(
        results,
        key=lambda x: (
            x["DecisionConfidence"],
            x["RiskScore"]
        ),
        reverse=True
    )

    return {
        "TopStocks": results[:10],
        "Mode": mode,
        "Version": "v2 - Two-Stage Analysis"
    }



@app.get("/track/{stock}")
def track(stock:str):

    data = backtest(stock)

    if data.get("Status") == "INVALID_STOCK":

        return data
    if data.get("EntryPrice", 0) == 0:

      return {
        "Status": "INVALID_PREDICTION",
        "Stock": stock,
        "Reason": "Backtest Not Reliable"
     }
    saved = save_prediction(data)

    if not saved:

        return {
           "Status": "ALREADY_TRACKED",
           "Stock": stock
        }

    
    return {
      "Status": "TRACKED",
      "Stock": stock,
      "EntryPrice": data["EntryPrice"],
      "Target": data["Target"],
      "StopLoss": data["StopLoss"]
   }

@app.get("/prediction_history")
def prediction_history():
    return {
        "History": load_predictions()
    }

# ── Canonical accuracy endpoint (Phase 1) ───────────────────────────────────
@app.get("/accuracy")
def accuracy():
    """
    Canonical accuracy endpoint.
    Uses persisted Status values only – does NOT call Yahoo Finance.
    """
    return calculate_accuracy()

# ── Backward-compatible alias ────────────────────────────────────────────────
@app.get("/history_stats")
def history_stats():
    """Alias for /accuracy – kept for backward compatibility."""
    return calculate_accuracy()

@app.get("/predictions")
def predictions():
    return {
        "Predictions": load_predictions()
    }

@app.get("/prediction_status/{stock}")
def prediction_status(stock: str):
    preds = load_predictions()
    for item in preds:
        if item["Stock"] == stock:
            return {
                "Stock": stock,
                "Status": check_prediction(item)
            }
    return {
        "Status": "NOT_TRACKED",
        "Stock": stock
    }

# ── GET /open_trades – Phase 1 ───────────────────────────────────────────────
@app.get("/open_trades")
def open_trades():
    """
    Return all predictions that are currently OPEN
    (not yet resolved and not expired).
    """
    trades = get_open_trades()
    return {
        "OpenTrades": trades,
        "Count": len(trades)
    }

# ── GET /monitor – Phase 1 ──────────────────────────────────────────────────
@app.get("/monitor")
def monitor():
    """
    For each OPEN prediction, fetch the latest price via CoinGecko/fetch_ohlcv
    and resolve WIN / LOSS / EXPIRED.  Returns the updated prediction list.
    """
    trades = get_open_trades()
    resolved = []
    errors = []

    for trade in trades:
        stock = trade["Stock"]
        try:
            # Fetch latest 1h data for live price check
            df = fetch_ohlcv(stock, timeframe="1h")
            if df.empty:
                errors.append({"Stock": stock, "Error": "no data"})
                continue

            current_price = float(df["Close"].iloc[-1].item())
            updated = resolve_prediction(stock, current_price)
            if updated:
                resolved.append(updated)
        except Exception as e:
            errors.append({"Stock": stock, "Error": str(e)})

    return {
        "Resolved": resolved,
        "Errors": errors,
        "Stats": calculate_accuracy()
    }

# ── DELETE /prediction_history – Phase 1 ────────────────────────────────────
# ── GET /dashboard_stats – Phase 3 ─────────────────────────────────────────
@app.get("/dashboard_stats")
def dashboard_stats():
    """
    Aggregate accuracy statistics for the Analytics Dashboard.
    Returns Total, Wins, Losses, Open, Expired and Accuracy %.
    """
    stats = calculate_accuracy()
    return {
        "Total":    stats["Total"],
        "Wins":     stats["Wins"],
        "Losses":   stats["Losses"],
        "Open":     stats["Open"],
        "Expired":  stats["Expired"],
        "Accuracy": stats["Accuracy"],
    }


# ── GET /mode_accuracy – Phase 3 ────────────────────────────────────────────
@app.get("/mode_accuracy")
def mode_accuracy():
    """
    Per-mode (INTRADAY / SWING) win/loss counts and accuracy percentages.
    """
    return get_mode_accuracy()


# ── GET /accuracy_trend – Phase 3 ───────────────────────────────────────────
@app.get("/accuracy_trend")
def accuracy_trend(limit: int = 20):
    """
    Last `limit` resolved predictions with a running-accuracy timeline.
    Used to power the Accuracy Trend Chart on the Analytics Dashboard.
    """
    if limit < 1 or limit > 200:
        limit = 20
    return get_accuracy_trend(limit)


from fastapi import HTTPException, Body

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 0 — Stock Selection Engine
# Returns the scanner results enriched with full analysis metadata
# so the frontend can display a ranked pick list.
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/stage0/scanner")
def stage0_scanner(mode: str = "INTRADAY"):
    """
    Stage 0: Stock / Coin Selection Engine.
    Runs backtest on every configured symbol, derives a signal and trade setup,
    enriches with live prices, and returns a ranked pick list.

    Works reliably even when the two-stage analyze() pipeline returns NO TRADE,
    because it reads directly from the backtest engine which always has data.
    """
    REQUESTS.inc()
    _log("INFO", event="stage0_scan_start", mode=mode)

    # ── Fetch live prices once for all symbols ────────────────────────────
    try:
        coin_ids = list(SYMBOL_TO_COINGECKO.values())
        live_data_raw = fetch_live_prices(coin_ids)
        live_by_symbol = {}
        for sym, cg_id in SYMBOL_TO_COINGECKO.items():
            live_by_symbol[sym] = live_data_raw.get(cg_id, {})
    except Exception as e:
        _log("ERROR", event="stage0_live_prices_failed", error=str(e))
        live_by_symbol = {}

    results = []

    for stock in SCAN_STOCKS:
        try:
            bt = backtest(stock, mode=mode)

            # Skip hard errors
            if bt.get("Status") == "INVALID_STOCK" or bt.get("error"):
                continue

            conf      = bt.get("Confidence",   0) or 0
            risk      = bt.get("RiskScore",     0) or 0
            win_rate  = bt.get("WinRate",       0) or 0
            pf        = bt.get("ProfitFactor",  0) or 0
            sharpe    = bt.get("Sharpe",        0) or 0
            adr       = bt.get("ADX",           0) or 0
            rsi_val   = bt.get("RSI",          50) or 50
            entry     = bt.get("EntryPrice",    0) or 0
            sl        = bt.get("StopLoss",      0) or 0
            target    = bt.get("Target",        0) or 0
            atr       = bt.get("ATR",           0) or 0
            rr        = bt.get("RiskReward",    0) or 0
            signal    = bt.get("Signal",        "SELL")
            mode_used = bt.get("Mode",          mode)

            # Use live price if available
            live = live_by_symbol.get(stock, {})
            live_price = live.get("price") or entry

            # Build TP1 / TP2 / TP3 from ATR multiples
            if signal == "BUY" or signal == "LONG":
                direction = "LONG"
                tp1 = round(entry + atr * 1.5, 2) if atr else target
                tp2 = round(entry + atr * 2.0, 2) if atr else target
                tp3 = round(entry + atr * 3.0, 2) if atr else target
                if mode_used == "SWING":
                    tp1 = round(entry + atr * 3.0, 2) if atr else target
                    tp2 = round(entry + atr * 4.0, 2) if atr else target
                    tp3 = round(entry + atr * 6.0, 2) if atr else target
                decision = "LONG"
            else:
                direction = "SHORT"
                tp1 = round(entry - atr * 1.5, 2) if atr else target
                tp2 = round(entry - atr * 2.0, 2) if atr else target
                tp3 = round(entry - atr * 3.0, 2) if atr else target
                if mode_used == "SWING":
                    tp1 = round(entry - atr * 3.0, 2) if atr else target
                    tp2 = round(entry - atr * 4.0, 2) if atr else target
                    tp3 = round(entry - atr * 6.0, 2) if atr else target
                decision = "SHORT"

            # Downgrade to WAIT if confidence is too low
            if conf < 50 or entry == 0:
                decision = "WAIT"

            # Composite score for ranking
            sharpe_sc = min(abs(sharpe) * 50, 100) if sharpe else 0
            composite = (
                conf      * 0.35 +
                risk      * 0.25 +
                min(win_rate, 100) * 0.20 +
                min(pf * 10, 100)  * 0.10 +
                sharpe_sc          * 0.10
            )

            # Build human reason string
            reasons = []
            if direction == "LONG":
                reasons.append(f"Bullish signal (ADX {round(adr,1)}, RSI {round(rsi_val,1)})")
            else:
                reasons.append(f"Bearish signal (ADX {round(adr,1)}, RSI {round(rsi_val,1)})")
            if conf >= 70:
                reasons.append(f"High confidence {conf}%")
            elif conf >= 50:
                reasons.append(f"Moderate confidence {conf}%")
            if pf >= 1.5:
                reasons.append(f"Profit factor {round(pf,2)}")

            results.append({
                "Symbol":             stock,
                "Decision":           decision,
                "Direction":          direction,
                "Signal":             signal,
                "Confidence":         conf,
                "DecisionConfidence": conf,
                "RiskScore":          risk,
                "WinRate":            win_rate,
                "ProfitFactor":       round(pf, 2),
                "Sharpe":             round(sharpe, 2),
                "ADX":                round(adr, 2),
                "RSI":                round(rsi_val, 2),
                "ATR":                round(atr, 4),
                "Entry":              round(entry, 4),
                "LivePrice":          round(live_price, 4) if live_price else entry,
                "StopLoss":           round(sl, 4),
                "TP1":                round(tp1, 4),
                "TP2":                round(tp2, 4),
                "TP3":                round(tp3, 4),
                "RiskReward":         round(rr, 2),
                "Mode":               mode_used,
                "Reason":             " | ".join(reasons),
                "CompositeScore":     round(composite, 2),
                "LiveData":           live,
            })

        except Exception as e:
            _log("ERROR", event="stage0_symbol_error", stock=stock, error=str(e))
            continue

    results.sort(key=lambda x: x["CompositeScore"], reverse=True)

    _log("INFO", event="stage0_scan_complete", mode=mode, count=len(results))

    return {
        "Stage": 0,
        "Label": "Stock Selection Engine",
        "Mode":  mode,
        "Count": len(results),
        "Picks": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — Advanced Market Intelligence Engine
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/stage1/analyze/{stock}")
def stage1_analyze(stock: str, mode: str = "INTRADAY"):
    """
    Stage 1: Advanced Market Intelligence.
    Runs full analysis: Price Action, SMC, Trend, Momentum, Volatility,
    Volume, Market Health, Multi-TF, AI Confidence, Risk, AI Summary.
    Never recommends a trade. Stage 2 makes that decision.
    """
    REQUESTS.inc()
    _log("INFO", event="stage1_analyze", stock=stock, mode=mode)

    sym = _normalize_symbol(stock)

    # ── 1. Fetch OHLCV data via Binance (fast, no rate limit) ─────────────
    from binance import fetch_ohlcv_binance, fetch_live_price_binance

    df_1h = fetch_ohlcv_binance(sym, "1h")
    df_1d = fetch_ohlcv_binance(sym, "1d")
    df_4h = fetch_ohlcv_binance(sym, "4h")
    df_15m= fetch_ohlcv_binance(sym, "15m")
    df_5m = fetch_ohlcv_binance(sym, "5m")

    # ── 2. Backtest metrics ────────────────────────────────────────────────
    try:
        bt = backtest(sym, mode=mode)
    except Exception as e:
        _log("ERROR", event="stage1_backtest_error", stock=sym, error=str(e))
        bt = {}

    bt_metrics = {
        "win_rate":       bt.get("WinRate",      0) or 0,
        "profit_factor":  bt.get("ProfitFactor", 0) or 0,
        "sharpe":         bt.get("Sharpe",        0) or 0,
        "max_drawdown":   bt.get("MaxDrawdown",   20) or 20,
    }

    # ── 3. Live price from Binance ─────────────────────────────────────────
    live = fetch_live_price_binance(sym)

    # ── 4. Run Stage 1 analysis engine ────────────────────────────────────
    multi_tf_dfs = {}
    for tf, df_tf in [("5m", df_5m), ("15m", df_15m), ("1h", df_1h), ("4h", df_4h), ("1D", df_1d)]:
        if df_tf is not None and not df_tf.empty:
            multi_tf_dfs[tf] = df_tf

    primary_df = df_1h if not df_1h.empty else df_1d

    if primary_df.empty:
        return {
            "Stage": 1, "Symbol": sym, "Error": "Insufficient OHLCV data",
            "summary": {"status": "Wait for Better Setup", "bias": "Neutral",
                        "strength": "Weak", "probability": 0}
        }

    cache = run_stage1_analysis(
        symbol=sym,
        df=primary_df,
        df_higher_tf=df_1d,
        timeframe="1h",
        backtest_metrics=bt_metrics,
        multi_tf_dfs=multi_tf_dfs,
    )

    # ── 5. Build flat response for the UI ─────────────────────────────────
    pa   = cache.get("price_action", {})
    smc  = cache.get("smc", {})
    tr   = cache.get("trend", {})
    mom  = cache.get("momentum", {})
    vol  = cache.get("volatility", {})
    volu = cache.get("volume", {})
    mh   = cache.get("market_health", {})
    mtf  = cache.get("multi_timeframe", {})
    conf = cache.get("confidence", {})
    risk = cache.get("risk", {})
    summ = cache.get("summary", {})

    live_price = live.get("price") or bt.get("EntryPrice", 0) or cache.get("current_price", 0)

    return {
        "Stage":   1,
        "Symbol":  sym,
        "Mode":    mode,

        # Price
        "LivePrice":   round(float(live_price), 4) if live_price else None,
        "EntryPrice":  round(float(live_price), 4) if live_price else None,
        "Change24h":   live.get("change_24h"),
        "Volume24h":   live.get("volume_24h"),
        "High24h":     live.get("high_24h"),
        "Low24h":      live.get("low_24h"),

        # Price Action
        "PA_Structure":  pa.get("structure"),
        "PA_Bias":       pa.get("structure_bias"),
        "PA_SwingHigh":  pa.get("swing_high"),
        "PA_SwingLow":   pa.get("swing_low"),
        "PA_HH":         pa.get("higher_high"),
        "PA_HL":         pa.get("higher_low"),
        "PA_LH":         pa.get("lower_high"),
        "PA_LL":         pa.get("lower_low"),
        "PA_BOS":        pa.get("bos"),
        "PA_CHoCH":      pa.get("choch"),

        # SMC
        "SMC_OB_Bull":   smc.get("order_block_bull"),
        "SMC_OB_Bear":   smc.get("order_block_bear"),
        "SMC_FVG_Bull":  smc.get("fvg_bull"),
        "SMC_FVG_Bear":  smc.get("fvg_bear"),
        "SMC_LiqHigh":   smc.get("liquidity_zone_high"),
        "SMC_LiqLow":    smc.get("liquidity_zone_low"),
        "SMC_Sweep":     smc.get("liquidity_sweep"),
        "SMC_Breaker":   smc.get("breaker_block"),
        "SMC_Mitigation":smc.get("mitigation_block"),

        # Trend
        "Trend":          tr.get("direction"),
        "EMA_Alignment":  tr.get("ema_alignment"),
        "EMA9":           tr.get("ema9"),
        "EMA21":          tr.get("ema21"),
        "EMA20":          tr.get("ema20"),
        "EMA50":          tr.get("ema50"),
        "EMA200":         tr.get("ema200"),
        "Supertrend":     tr.get("supertrend"),
        "Supertrend_val": tr.get("supertrend_val"),
        "ADX":            tr.get("adx"),
        "ADX_Strength":   tr.get("adx_strength"),
        "PlusDI":         tr.get("plus_di"),
        "MinusDI":        tr.get("minus_di"),
        "DI_Bias":        tr.get("di_bias"),
        "TrendScore":     tr.get("strength_score"),

        # Momentum
        "RSI":           mom.get("rsi"),
        "RSI_Zone":      mom.get("rsi_zone"),
        "MACD_Trend":    mom.get("macd_trend"),
        "MACD_Cross":    mom.get("macd_cross"),
        "StochRSI_K":    mom.get("stochrsi_k"),
        "StochRSI_Zone": mom.get("stochrsi_zone"),
        "StochRSI_Cross":mom.get("stochrsi_cross"),
        "CCI":           mom.get("cci"),
        "CCI_Signal":    mom.get("cci_signal"),
        "MomScore":      mom.get("score"),
        "MomLabel":      mom.get("label"),

        # Volatility
        "ATR":           vol.get("atr"),
        "ATR_Pct":       vol.get("atr_pct"),
        "ATR_State":     vol.get("atr_state"),
        "VolRegime":     vol.get("regime"),
        "BB_Upper":      vol.get("bb_upper"),
        "BB_Middle":     vol.get("bb_middle"),
        "BB_Lower":      vol.get("bb_lower"),
        "BB_Width":      vol.get("bb_width"),
        "BB_Position":   vol.get("bb_position"),
        "BB_Squeeze":    vol.get("bb_squeeze"),
        "KC_Upper":      vol.get("kc_upper"),
        "KC_Lower":      vol.get("kc_lower"),
        "HistVol":       vol.get("hist_vol"),

        # Volume
        "RVOL":          volu.get("rvol"),
        "VolTrend":      volu.get("trend"),
        "VolSpike":      volu.get("spike"),
        "BuyPressure":   volu.get("buy_pressure"),
        "SellPressure":  volu.get("sell_pressure"),
        "VWAP":          volu.get("vwap"),
        "PriceVsVWAP":   volu.get("price_vs_vwap"),

        # Market Health
        "BullScore":      mh.get("bull_score"),
        "BearScore":      mh.get("bear_score"),
        "NeutralScore":   mh.get("neutral_score"),
        "MarketHealth":   mh.get("label"),
        "HealthScore":    mh.get("overall_score"),

        # Multi-TF
        "MTF_5m":         mtf.get("timeframes", {}).get("5m", "Neutral"),
        "MTF_15m":        mtf.get("timeframes", {}).get("15m", "Neutral"),
        "MTF_1h":         mtf.get("timeframes", {}).get("1h", "Neutral"),
        "MTF_4h":         mtf.get("timeframes", {}).get("4h", "Neutral"),
        "MTF_1D":         mtf.get("timeframes", {}).get("1D", "Neutral"),
        "MTF_Bias":       mtf.get("overall_bias"),
        "MTF_Align":      mtf.get("alignment_score"),

        # AI Confidence
        "Confidence":     conf.get("score"),
        "ConfGrade":      conf.get("grade"),
        "ConfExplain":    conf.get("explanation"),

        # Risk
        "RiskScore":      risk.get("score"),
        "RiskCategory":   risk.get("category"),
        "PositionSize":   risk.get("position_size"),
        "MaxRiskPct":     risk.get("max_risk_pct"),
        "Leverage":       risk.get("leverage"),

        # Support / Resistance
        "Support":    cache.get("support"),
        "Resistance": cache.get("resistance"),

        # AI Summary
        "Bias":        summ.get("bias"),
        "Strength":    summ.get("strength"),
        "Probability": summ.get("probability"),
        "Status":      summ.get("status"),
        "Highlights":  summ.get("highlights"),

        # Legacy analysis fields. Stage 1 intentionally exposes no BUY/SELL
        # signal; trade decisions belong exclusively to Stage 2.
        "TrendStrength":   tr.get("adx_strength"),
        "MarketStructure": pa.get("structure"),
        "EMAAlignment":    tr.get("ema_alignment"),
        "Volatility":      vol.get("regime"),
        "WinRate":         bt_metrics["win_rate"],
        "ProfitFactor":    bt_metrics["profit_factor"],
        "Sharpe":          bt_metrics["sharpe"],
        "MaxDrawdown":     bt_metrics["max_drawdown"],
        "StopLoss":        bt.get("StopLoss", 0),
        "Target":          bt.get("Target", 0),
        "RiskReward":      bt.get("RiskReward", 0),
    }


# STAGE 2 — Trade Recommendation (dedicated endpoint)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/stage2/recommend/{stock}")
def stage2_recommend(stock: str, mode: str = "INTRADAY"):
    """
    Stage 2: Trade recommendation based on backtest data.
    Returns LONG / SHORT / WAIT with entry, SL, TP1/2/3 and reason.
    """
    REQUESTS.inc()
    _log("INFO", event="stage2_recommend", stock=stock, mode=mode)

    sym = _normalize_symbol(stock)

    try:
        bt = backtest(sym, mode=mode)
    except Exception as e:
        _log("ERROR", event="stage2_backtest_error", stock=sym, error=str(e))
        return {"Stage": 2, "Symbol": sym, "Decision": "NO TRADE",
                "Reason": f"Data error: {e}", "Confidence": 0}

    if bt.get("Status") == "INVALID_STOCK" or bt.get("error"):
        return {"Stage": 2, "Symbol": sym, "Decision": "NO TRADE",
                "Reason": bt.get("error", "Invalid symbol"), "Confidence": 0}

    entry   = bt.get("EntryPrice",   0) or 0
    atr     = bt.get("ATR",          0) or 0
    conf    = bt.get("Confidence",   0) or 0
    risk_sc = bt.get("RiskScore",    0) or 0
    signal  = bt.get("Signal",    "SELL")
    rr      = bt.get("RiskReward",   0) or 0
    sl      = bt.get("StopLoss",     0) or 0
    win_rate= bt.get("WinRate",      0) or 0
    pf      = bt.get("ProfitFactor", 0) or 0
    adx_val = bt.get("ADX",          0) or 0
    rsi_val = bt.get("RSI",         50) or 50

    # Direction
    direction = "LONG" if signal in ("BUY", "STRONG BUY") else "SHORT"

    # Build TP levels from ATR
    if direction == "LONG":
        if mode == "SWING":
            tp1 = round(entry + atr * 3.0, 4)
            tp2 = round(entry + atr * 4.0, 4)
            tp3 = round(entry + atr * 6.0, 4)
        else:
            tp1 = round(entry + atr * 1.5, 4)
            tp2 = round(entry + atr * 2.0, 4)
            tp3 = round(entry + atr * 3.0, 4)
    else:
        if mode == "SWING":
            tp1 = round(entry - atr * 3.0, 4)
            tp2 = round(entry - atr * 4.0, 4)
            tp3 = round(entry - atr * 6.0, 4)
        else:
            tp1 = round(entry - atr * 1.5, 4)
            tp2 = round(entry - atr * 2.0, 4)
            tp3 = round(entry - atr * 3.0, 4)

    # Recalc RR from TP2
    risk_amt   = abs(entry - sl)
    reward_amt = abs(tp2 - entry)
    rr_calc    = round(reward_amt / risk_amt, 2) if risk_amt > 0 else rr

    # Decision thresholds
    reasons = []
    if entry == 0 or atr == 0:
        decision = "NO TRADE"
        reasons  = ["Insufficient price data from backtest"]
    elif conf >= 65 and win_rate >= 50:
        decision = direction
        reasons  = [
            f"{direction} signal on {sym}",
            f"Confidence {conf}%",
            f"Win rate {round(win_rate,1)}%",
            f"ADX {round(adx_val,1)} — {'trending' if adx_val>=25 else 'weak trend'}",
            f"RSI {round(rsi_val,1)} — {('oversold, potential bounce' if rsi_val<35 else 'overbought, potential drop' if rsi_val>70 else 'neutral zone')}",
            f"Profit factor {round(pf,2)}",
        ]
    elif conf >= 50:
        decision = "WAIT"
        reasons  = [
            f"Setup developing — confidence {conf}% (need ≥65%)",
            f"Win rate {round(win_rate,1)}% (need ≥50%)",
            "Wait for stronger confirmation",
        ]
    else:
        decision = "NO TRADE"
        reasons  = [
            f"Low confidence: {conf}%",
            f"Win rate: {round(win_rate,1)}%",
            "No reliable trade setup at this time",
        ]

    return {
        "Stage":      2,
        "Symbol":     sym,
        "Mode":       mode,
        "Decision":   decision,
        "Direction":  direction,
        "Confidence": conf,
        "RiskScore":  risk_sc,
        "Entry":      round(entry, 4),
        "StopLoss":   round(sl, 4),
        "TP1":        tp1,
        "TP2":        tp2,
        "TP3":        tp3,
        "Risk":       round(risk_amt, 4),
        "Reward":     round(reward_amt, 4),
        "RiskReward": rr_calc,
        "WinRate":    win_rate,
        "Reason":     " | ".join(reasons),
    }


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3 — Lock Position
# Stores the confirmed trade setup in memory.
# Once locked, Stage 4 uses this as the reference.
# ─────────────────────────────────────────────────────────────────────────────

# In-memory lock store (keyed by symbol)
import threading
_LOCK_STORE: dict = {}
_LOCK_MUTEX = threading.Lock()


@app.post("/stage3/lock")
def stage3_lock(payload: dict = Body(...)):
    """
    Stage 3: Lock a trade position.

    Expected body:
      {
        "symbol":    "BTC-USD",
        "direction": "LONG" | "SHORT",
        "entry":     float,
        "stop_loss": float,
        "tp1":       float,
        "tp2":       float,
        "tp3":       float,
        "confidence": float,
        "reason":    str
      }

    Returns the locked position object with lock timestamp.
    """
    from datetime import datetime as _dt

    symbol = payload.get("symbol", "").upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")

    required = ["direction", "entry", "stop_loss", "tp1", "tp2", "tp3"]
    for field in required:
        if field not in payload:
            raise HTTPException(status_code=400, detail=f"Missing field: {field}")

    entry     = float(payload["entry"])
    stop_loss = float(payload["stop_loss"])
    tp1       = float(payload["tp1"])
    tp2       = float(payload["tp2"])
    tp3       = float(payload["tp3"])
    direction = str(payload["direction"]).upper()

    risk   = abs(entry - stop_loss)
    reward = abs(tp2 - entry)
    rr     = round(reward / risk, 2) if risk > 0 else 0

    locked = {
        "symbol":        symbol,
        "direction":     direction,
        "entry":         round(entry, 6),
        "stop_loss":     round(stop_loss, 6),
        "tp1":           round(tp1, 6),
        "tp2":           round(tp2, 6),
        "tp3":           round(tp3, 6),
        "risk":          round(risk, 6),
        "reward":        round(reward, 6),
        "risk_reward":   rr,
        "confidence":    payload.get("confidence", 0),
        "reason":        payload.get("reason", ""),
        "locked_at":     _dt.utcnow().isoformat() + "Z",
        "status":        "LOCKED",
        "mode":          payload.get("mode", "INTRADAY"),
    }

    with _LOCK_MUTEX:
        _LOCK_STORE[symbol] = locked

    _log("INFO", event="position_locked", symbol=symbol,
         direction=direction, entry=entry)

    return {
        "Stage":    3,
        "Label":    "Lock Position",
        "Status":   "LOCKED",
        "Position": locked,
    }


@app.get("/stage3/position/{symbol}")
def stage3_get_position(symbol: str):
    """Return the currently locked position for a symbol, or 404."""
    sym = symbol.upper()
    with _LOCK_MUTEX:
        pos = _LOCK_STORE.get(sym)
    if not pos:
        raise HTTPException(status_code=404, detail=f"No locked position for {sym}")
    return {"Stage": 3, "Position": pos}


@app.delete("/stage3/unlock/{symbol}")
def stage3_unlock(symbol: str):
    """Unlock/close a position. Called after the trade is closed."""
    sym = symbol.upper()
    with _LOCK_MUTEX:
        pos = _LOCK_STORE.pop(sym, None)
    if not pos:
        raise HTTPException(status_code=404, detail=f"No locked position for {sym}")
    _log("INFO", event="position_unlocked", symbol=sym)
    return {"Stage": 3, "Status": "UNLOCKED", "Symbol": sym}


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 4 — AI Protection Manager
# Monitors an active locked position and returns a single action recommendation.
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/stage4/protect/{symbol}")
def stage4_protect(symbol: str):
    """
    Stage 4: AI Protection Manager.

    Reads the locked position from Stage 3, fetches the live price,
    runs all protection logic and returns ONE recommendation:

      HOLD | HOLD STRONG | MOVE STOP LOSS | ENABLE TRAILING STOP |
      PARTIAL EXIT | TAKE PROFIT | EXIT NOW

    Always returns a human-readable WHY explanation.
    """
    REQUESTS.inc()
    sym = symbol.upper()

    # ── Require a locked position ─────────────────────────────────────────
    with _LOCK_MUTEX:
        pos = _LOCK_STORE.get(sym)
    if not pos:
        raise HTTPException(
            status_code=404,
            detail=f"No locked position for {sym}. Lock a trade first (Stage 3)."
        )

    # ── Fetch live price and current indicators ───────────────────────────
    try:
        df = fetch_ohlcv(sym, timeframe=BACKTEST_INTERVAL)
        if df.empty or len(df) < 30:
            raise ValueError("Insufficient OHLCV data")
        df = add_indicators(df)

        df1h = fetch_ohlcv(sym, timeframe=TREND_INTERVAL)
    except Exception as e:
        YF_ERRORS.inc()
        return {
            "Stage":          4,
            "Symbol":         sym,
            "Action":         "HOLD",
            "Reason":         f"Data fetch error — defaulting to HOLD. ({e})",
            "Position":       pos,
            "LivePrice":      None,
            "PnL":            None,
        }

    current_price  = round(float(df["Close"].iloc[-1].item()), 6)
    atr            = round(float(df["ATR"].iloc[-1].item()), 6) if "ATR" in df.columns else 0.0
    rsi            = round(float(df["RSI"].iloc[-1].item()), 2) if "RSI" in df.columns else 50.0
    adx            = round(float(df["ADX"].iloc[-1].item()), 2) if "ADX" in df.columns else 0.0
    macd_val       = round(float(df["MACD"].iloc[-1].item()), 6) if "MACD" in df.columns else 0.0
    macd_sig       = round(float(df["MACD_Signal"].iloc[-1].item()), 6) if "MACD_Signal" in df.columns else 0.0

    # Higher timeframe trend
    higher_tf_bull = (
        market_trend(df1h["Close"])
        if not df1h.empty and len(df1h) >= 2
        else True
    )

    # ── Position metrics ──────────────────────────────────────────────────
    entry     = pos["entry"]
    stop_loss = pos["stop_loss"]
    tp1       = pos["tp1"]
    tp2       = pos["tp2"]
    tp3       = pos["tp3"]
    direction = pos["direction"]   # "LONG" or "SHORT"
    locked_at = pos["locked_at"]

    from datetime import datetime as _dt
    try:
        lock_time  = _dt.fromisoformat(locked_at.rstrip("Z"))
        hold_mins  = round((_dt.utcnow() - lock_time).total_seconds() / 60, 1)
    except Exception:
        hold_mins  = 0.0

    if direction == "LONG":
        pnl_pct        = round((current_price - entry) / entry * 100, 3)
        dist_to_tp1    = round(tp1 - current_price, 6)
        dist_to_tp2    = round(tp2 - current_price, 6)
        dist_to_tp3    = round(tp3 - current_price, 6)
        dist_to_sl     = round(current_price - stop_loss, 6)
        past_tp1       = current_price >= tp1
        past_tp2       = current_price >= tp2
        past_tp3       = current_price >= tp3
        sl_hit         = current_price <= stop_loss
        momentum_ok    = (macd_val > macd_sig) and (rsi > 45) and higher_tf_bull
        reversal_warn  = (macd_val < macd_sig) and (rsi > 65)
    else:   # SHORT
        pnl_pct        = round((entry - current_price) / entry * 100, 3)
        dist_to_tp1    = round(current_price - tp1, 6)
        dist_to_tp2    = round(current_price - tp2, 6)
        dist_to_tp3    = round(current_price - tp3, 6)
        dist_to_sl     = round(stop_loss - current_price, 6)
        past_tp1       = current_price <= tp1
        past_tp2       = current_price <= tp2
        past_tp3       = current_price <= tp3
        sl_hit         = current_price >= stop_loss
        momentum_ok    = (macd_val < macd_sig) and (rsi < 55) and (not higher_tf_bull)
        reversal_warn  = (macd_val > macd_sig) and (rsi < 35)

    at_breakeven   = abs(current_price - entry) <= atr * 0.5
    high_volatility = atr > 0 and (atr / current_price * 100) > 3.0

    # ── Protection decision logic ─────────────────────────────────────────
    action = "HOLD"
    reason = "Position is active. Monitoring market conditions."

    if sl_hit:
        action = "EXIT NOW"
        reason = "Stop loss has been hit. Exit immediately to protect capital."

    elif past_tp3:
        action = "TAKE PROFIT"
        reason = f"Price has reached TP3 ({tp3}). Full profit target achieved. Consider closing the full position."

    elif past_tp2:
        if momentum_ok and adx >= 25:
            action = "HOLD STRONG"
            reason = f"TP2 ({tp2}) reached. Momentum remains strong (ADX {adx}, RSI {rsi}). Hold for TP3."
        else:
            action = "TAKE PROFIT"
            reason = f"TP2 ({tp2}) reached and momentum is fading. Take profit now."

    elif past_tp1:
        if reversal_warn:
            action = "PARTIAL EXIT"
            reason = f"TP1 ({tp1}) reached. Reversal signals detected (RSI {rsi}, MACD diverging). Take 50% profit."
        elif momentum_ok:
            action = "MOVE STOP LOSS"
            reason = f"TP1 ({tp1}) reached with strong momentum. Move stop loss to break-even ({entry}) to protect profit."
        else:
            action = "PARTIAL EXIT"
            reason = f"TP1 ({tp1}) reached. Take 50% profit here and trail the remainder."

    elif at_breakeven and not momentum_ok:
        action = "MOVE STOP LOSS"
        reason = f"Price near entry. Move stop loss to break-even ({entry}) to eliminate risk."

    elif reversal_warn:
        action = "EXIT NOW"
        reason = f"Bearish reversal confirmed (MACD crossed, RSI {rsi}). Exit now to protect capital."

    elif high_volatility:
        action = "ENABLE TRAILING STOP"
        reason = f"High volatility detected (ATR {round(atr/current_price*100,2)}% of price). Enable trailing stop to lock in gains."

    elif pnl_pct < -1.5 and hold_mins > 60:
        action = "EXIT NOW"
        reason = f"Position down {abs(pnl_pct):.2f}% after {hold_mins} min. Risk is increasing. Exit to stop the loss."

    elif pnl_pct > 0 and momentum_ok and adx >= 25:
        action = "HOLD STRONG"
        reason = f"Momentum strong (ADX {adx}, RSI {rsi}). Trend intact. Hold position and let it run."

    elif pnl_pct > 0 and not momentum_ok:
        action = "HOLD"
        reason = f"In profit (+{pnl_pct:.2f}%) but momentum is slowing. Hold with caution. Watch closely."

    else:
        action = "HOLD"
        reason = f"No clear exit signal. Monitor price vs SL ({stop_loss}) and TP1 ({tp1})."

    return {
        "Stage":           4,
        "Label":           "AI Protection Manager",
        "Symbol":          sym,
        "Action":          action,
        "Reason":          reason,
        "LivePrice":       current_price,
        "PnL":             pnl_pct,
        "HoldingMins":     hold_mins,
        "Indicators": {
            "RSI":          rsi,
            "ADX":          adx,
            "MACD":         macd_val,
            "MACD_Signal":  macd_sig,
            "ATR":          atr,
            "HigherTF":     "BULLISH" if higher_tf_bull else "BEARISH",
        },
        "Distances": {
            "to_TP1":       dist_to_tp1,
            "to_TP2":       dist_to_tp2,
            "to_TP3":       dist_to_tp3,
            "to_SL":        dist_to_sl,
        },
        "Position":        pos,
    }


@app.delete("/prediction_history")
def delete_prediction_history():
    """Wipe all prediction history.  Irreversible."""
    ok = clear_predictions()
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to clear history")
    return {"Status": "CLEARED", "Message": "All prediction history deleted"}
