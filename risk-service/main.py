from fastapi import FastAPI
import yfinance as yf

app=FastAPI()

@app.get("/risk/{symbol}")
def risk(symbol):

    df=yf.download(symbol,period="1d")

    price=float(df["Close"].iloc[-1])

    return {

        "Entry":price,

        "Stoploss":
        round(price*.99,2),

        "Target":
        round(price*1.02,2)

    }
