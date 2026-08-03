from fastapi import FastAPI
from candle_fetch import get_market

app = FastAPI()

@app.get("/")
def home():

    return {
        "service":"market-data",
        "status":"running"
    }

@app.get("/market")
def market():

    return get_market().to_dict()
