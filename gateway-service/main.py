from fastapi import FastAPI
import requests

app = FastAPI()


@app.get("/analysis/{stock}")
def analysis(stock: str):

    try:

        indicator = requests.get(
            f"http://indicator:8001/indicator/{stock}",
            timeout=10
        ).json()

        risk = requests.get(
            f"http://risk:8002/risk/{stock}",
            timeout=10
        ).json()

        prediction = requests.get(
            f"http://prediction:8004/predict/{stock}",
            timeout=10
        ).json()

        confidence = requests.get(
            f"http://confidence:8005/confidence/{stock}",
            timeout=10
        ).json()

        return {
            "Indicator": indicator,
            "Risk": risk,
            "Prediction": prediction,
            "Confidence": confidence
        }

    except Exception as e:

        return {
            "error": str(e)
        }
