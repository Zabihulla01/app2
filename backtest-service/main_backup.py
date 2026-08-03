from fastapi import FastAPI
import yfinance as yf
import ta
import numpy as np

app = FastAPI()


@app.get("/backtest/{stock}")
def backtest(

    stock:str,

    adx_min:int=25,

    hold:int=12,

    target_rr:float=2

):


    df=yf.download(

        stock,

        period="60d",

        interval="15m",

        auto_adjust=True

    )


    df1h=yf.download(

        stock,

        period="60d",

        interval="1h",

        auto_adjust=True

    )


    if len(df)<250:

        return {

            "error":

            "Not enough data"

        }



    close=df["Close"].squeeze()
    high=df["High"].squeeze()
    low=df["Low"].squeeze()
    volume=df["Volume"].squeeze()



    close1h=df1h["Close"].squeeze()



    ema50_1h=close1h.rolling(50).mean()

    ema200_1h=close1h.rolling(200).mean()



    bull_1h=(

        ema50_1h.iloc[-1]

        >

        ema200_1h.iloc[-1]

    )



    df["EMA50"]=close.rolling(50).mean()

    df["EMA200"]=close.rolling(200).mean()

    df["AVG_VOL"]=volume.rolling(20).mean()

    df["MACD"]=ta.trend.MACD(close).macd()



    df["ADX"]=ta.trend.ADXIndicator(

        high,

        low,

        close

    ).adx()



    df["RSI"]=ta.momentum.RSIIndicator(

        close

    ).rsi()



    df["ATR"]=ta.volatility.AverageTrueRange(

        high,

        low,

        close

    ).average_true_range()



    df["SUPPORT"]=low.rolling(

        20

    ).min()



    df["RESISTANCE"]=high.rolling(

        20

    ).max()



    wins=0
    losses=0

    gp=0
    gl=0

    returns=[]



    for i in range(

        200,

        len(df)-hold

    ):



        current=close.iloc[i]

        future=close.iloc[i+hold]



        signal="HOLD"



        if (

            df["EMA50"].iloc[i]

            >

            df["EMA200"].iloc[i]

            and

            df["MACD"].iloc[i]

            >

            0

            and

            df["ADX"].iloc[i]

            >

            adx_min

            and

            35

            <

            df["RSI"].iloc[i]

            <

            70

            and

            volume.iloc[i]

            >

            df["AVG_VOL"].iloc[i]

            and

            current

            >

            df["SUPPORT"].iloc[i]

            and

            bull_1h

        ):



            signal="BUY"



        elif (

            df["EMA50"].iloc[i]

            <

            df["EMA200"].iloc[i]

            and

            df["MACD"].iloc[i]

            <

            0

            and

            df["ADX"].iloc[i]

            >

            adx_min

            and

            current

            <

            df["RESISTANCE"].iloc[i]

            and

            not bull_1h

        ):



            signal="SELL"



        if signal=="HOLD":

            continue



        move=(

            future-current

        ) if signal=="BUY" else (

            current-future

        )



        atr=df["ATR"].iloc[i]



        target=target_rr*atr

        stop=atr



        if move>=target:

            profit=target_rr


        elif move<=-stop:

            profit=-1


        else:

            profit=(

                move/current

            )*100



        returns.append(

            profit

        )



        if profit>0:

            wins+=1

            gp+=profit


        else:

            losses+=1

            gl+=abs(

                profit

            )



    total=wins+losses



    pf=(

        gp/gl

    ) if gl else 0



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



    maxdd=0


    if len(cumulative):


        peak=np.maximum.accumulate(

            cumulative

        )


        dd=peak-cumulative


        maxdd=np.max(dd)



    return {

        "Trades":

        total,


        "WinRate":

        round(

            wins/

            total*100,

            2

        ) if total else 0,


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

        round(
            float(maxdd),
            2
        )

    }



@app.get("/optimize/{stock}")

def optimize(

    stock:str

):


    results=[]



    for adx in [

        20,

        25,

        30

    ]:



        for hold in [

            5,

            8,

            12

        ]:



            for rr in [

                2,

                3

            ]:



                r=backtest(

                    stock,

                    adx,

                    hold,

                    rr

                )



                if (

                    "ProfitFactor"

                    in r

                ):



                    results.append({

                        "adx":adx,

                        "hold":hold,

                        "rr":rr,

                        "pf":

                        r["ProfitFactor"],

                        "sharpe":

                        r["Sharpe"]

                    })



    return sorted(

        results,

        key=lambda x:

        x["pf"],

        reverse=True

    )[:10]



@app.get("/optimize_all")

def optimize_all():


    stocks=[

        "AAPL",

        "MSFT",

        "GOOGL",

        "AMZN",

        "RELIANCE.NS",

        "TCS.NS",

        "INFY.NS"

    ]


    results=[]


    for stock in stocks:


        results.append({

            "Stock":

            stock,

            **backtest(stock)

        })


    return sorted(

        results,

        key=lambda x:

        x.get(

            "ProfitFactor",

            0

        ),

        reverse=True

    )
