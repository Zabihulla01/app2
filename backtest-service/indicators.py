import ta


def add_indicators(df):

    close = df["Close"].squeeze()

    high = df["High"].squeeze()

    low = df["Low"].squeeze()

    volume = df["Volume"].squeeze()



    df["EMA50"] = (

        close

        .rolling(50)

        .mean()

    )



    df["EMA200"] = (

        close

        .rolling(200)

        .mean()

    )



    df["AVG_VOL"] = (

        volume

        .rolling(20)

        .mean()

    )

    df["VWAP"] = (
    (close * volume).cumsum()
    /
    volume.cumsum()
)



    df["MACD"] = (

        ta.trend.MACD(

            close

        )

        .macd()

    )



    df["ADX"] = (

        ta.trend.ADXIndicator(

            high,

            low,

            close

        )

        .adx()

    )



    df["RSI"] = (

        ta.momentum.RSIIndicator(

            close

        )

        .rsi()

    )



    df["ATR"] = (

        ta.volatility.AverageTrueRange(

            high,

            low,

            close

        )

        .average_true_range()

    )



    df["SUPPORT"] = (

        low

        .rolling(20)

        .min()

    )



    df["RESISTANCE"] = (

        high

        .rolling(20)

        .max()

    )



    return df
