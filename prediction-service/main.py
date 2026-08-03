from fastapi import FastAPI
import requests
import numpy as np

app = FastAPI()


@app.get(
"/predict/{stock}"
)

def predict(
stock:str
):

    try:

        data = requests.get(

        f"http://indicator:8001/indicator/{stock}"

        ).json()


        score = 0


        # RSI trend

        if data["RSI"] < 35:

            score += 25

        elif data["RSI"] > 70:

            score -= 25



        # MACD momentum

        if data["MACD"] > 0:

            score += 20

        else:

            score -= 20



        # Trend strength

        if data["ADX"] > 25:

            score += 20

        elif data["ADX"] > 15:

            score += 10



        # Volatility

        if data["ATR"] < 35:

            score += 10



        # Volume

        if data["Volume"] > 10000000:

            score += 10



        # Bollinger trend

        if data["EMA20"] > data["BB_Lower"]:

            score += 15



        prediction = "HOLD"


        if score >= 60:

            prediction = "BUY"


        elif score <= 20:

            prediction = "SELL"



        return {

        "Prediction":
        prediction,


        "Score":
        score,


        "Trend":

        "Strong"

        if data["ADX"] > 25

        else

        "Weak",


        "Analysis":{

        "RSI":
        data["RSI"],


        "MACD":
        data["MACD"],


        "ADX":
        data["ADX"],


        "ATR":
        data["ATR"]

        }

        }


    except Exception as e:

        return {

        "error":

        str(e)

        }
