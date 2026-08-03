from fastapi import FastAPI
import requests

app = FastAPI()


@app.get(

"/confidence/{stock}"

)

def confidence(

stock:str

):


    try:


        data = requests.get(

        f"http://indicator:8001/indicator/{stock}"

        ).json()



        score = 0



        # RSI

        if data["RSI"] < 30:

            score += 25


        elif data["RSI"] < 50:

            score += 10




        # MACD

        if data["MACD"] > 0:

            score += 20




        # ADX

        if data["ADX"] > 25:

            score += 20


        elif data["ADX"] > 15:

            score += 10




        # ATR

        if data["ATR"] < 35:

            score += 10




        # Volume

        if data["Volume"] > 10000000:

            score += 10




        # Bollinger

        if (

        data["EMA20"]

        >

        data["BB_Lower"]

        ):

            score += 15




        level = "Low"



        if score >= 70:

            level = "High"



        elif score >= 40:

            level = "Medium"




        return {


        "Confidence":

        score,



        "Level":

        level,



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

        str(

        e

        )

        }
