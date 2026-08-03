from fastapi import FastAPI
import yfinance as yf
import ta

from cachetools import TTLCache


app = FastAPI()


cache = TTLCache(

maxsize=20,

ttl=55

)



@app.get(

"/indicator/{stock}"

)

def indicator(

stock:str

):


    try:


        if stock in cache:

            return cache[stock]



        df = yf.download(

        stock,

        period="6mo",

        interval="1d"

        )



        close = (

        df["Close"]

        .squeeze()

        )



        high = (

        df["High"]

        .squeeze()

        )



        low = (

        df["Low"]

        .squeeze()

        )



        volume = (

        df["Volume"]

        .squeeze()

        )





        rsi = (

        ta.momentum

        .RSIIndicator(

        close

        )

        .rsi()

        .iloc[-1]

        )





        ema20 = (

        ta.trend

        .EMAIndicator(

        close,

        20

        )

        .ema_indicator()

        .iloc[-1]

        )






        macd = (

        ta.trend

        .MACD(

        close

        )

        .macd()

        .iloc[-1]

        )







        atr = (

        ta.volatility

        .AverageTrueRange(

        high,

        low,

        close

        )

        .average_true_range()

        .iloc[-1]

        )







        adx = (

        ta.trend

        .ADXIndicator(

        high,

        low,

        close

        )

        .adx()

        .iloc[-1]

        )








        bb = (

        ta.volatility

        .BollingerBands(

        close

        )

        )






        result = {


        "RSI":

        round(

        rsi,

        2

        ),




        "EMA20":

        round(

        ema20,

        2

        ),




        "MACD":

        round(

        macd,

        2

        ),




        "ATR":

        round(

        atr,

        2

        ),




        "ADX":

        round(

        adx,

        2

        ),




        "BB_Upper":

        round(

        bb

        .bollinger_hband()

        .iloc[-1],

        2

        ),




        "BB_Lower":

        round(

        bb

        .bollinger_lband()

        .iloc[-1],

        2

        ),




        "Volume":

        int(

        volume

        .iloc[-1]

        )



        }




        cache[

        stock

        ] = result




        return result




    except Exception as e:



        return {

        "error":

        str(

        e

        )

        }
