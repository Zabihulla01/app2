import yfinance as yf

def get_market():

    data = yf.download(
        "^NSEI",
        period="1d",
        interval="5m"
    )

    return data.tail(20)
