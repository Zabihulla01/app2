from fastapi import FastAPI
import yfinance as yf

app = FastAPI()


@app.get("/pattern")
def pattern():

    df = yf.download(
        "^NSEI",
        period="1d",
        interval="5m",
        auto_adjust=True
    )

    if df.empty:
        return {"error":"No market data"}

    candle = df.iloc[-1]

    open_ = float(candle["Open"])
    close = float(candle["Close"])
    high = float(candle["High"])
    low = float(candle["Low"])

    body = abs(close-open_)
    upper = high-max(open_,close)
    lower = min(open_,close)-low


    if lower > body*2:
        signal="Hammer"

    elif body < (high-low)*0.1:
        signal="Doji"

    else:
        signal="Normal"


    return {

        "Pattern":signal,
        "Open":open_,
        "Close":close,
        "High":high,
        "Low":low

    }
