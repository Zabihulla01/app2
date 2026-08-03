from fastapi import FastAPI
import requests

app = FastAPI()


@app.get("/decision/{stock}")

def decision(stock: str):

    try:

        analysis = requests.get(
            f"http://gateway:8000/analysis/{stock}"
        ).json()


        prediction = analysis[
            "Prediction"
        ]["Prediction"]


        confidence = analysis[
            "Confidence"
        ]["Confidence"]


        adx = analysis[
            "Indicator"
        ]["ADX"]



        signal = "HOLD"



        if (
            prediction == "BUY"
            and confidence >= 70
            and adx > 25
        ):

            signal = "STRONG BUY"



        elif (
            prediction == "BUY"
            and confidence >= 50
        ):

            signal = "BUY"



        elif (
            prediction == "SELL"
            and confidence >= 70
            and adx > 25
        ):

            signal = "STRONG SELL"



        elif (
            prediction == "SELL"
            and confidence >= 50
        ):

            signal = "SELL"



        return {

            "Signal":
            signal,


            "Confidence":
            confidence,


            "Analysis":
            analysis

        }



    except Exception as e:

        return {

            "error":
            str(e)

        }
