def generate_signal(
    df,
    i,
    adx_min,
    bull_1h
):

    ema50 = float(
        df["EMA50"].iloc[i]
    )

    ema200 = float(
        df["EMA200"].iloc[i]
    ) if not (
        df["EMA200"].isna().iloc[i]
    ) else ema50


    macd = float(
        df["MACD"].iloc[i]
    )


    adx = float(
        df["ADX"].iloc[i]
    )


    rsi = float(
        df["RSI"].iloc[i]
    )

    price = float(
        df["Close"].iloc[i].item() 
    )

    vwap = float(
        df["VWAP"].iloc[i]
    )

    volume_now = float(
       df["Volume"].iloc[i].item() 
    )

    avg_volume = float(
       df["AVG_VOL"].iloc[i].item() 
   )


    buy = (

    ema50 >= ema200

    and

    macd > -0.2

    and

    adx > (
        adx_min * 0.8
    )

    and

    30 < rsi < 75

    and

    price > vwap

    and

    volume_now > avg_volume * 1.5
    and bull_1h
)


    sell = (

        ema50 <= ema200

        and

        macd < 0.2

        and

        adx > (

            adx_min * 0.8

        )

        and

        25 < rsi < 70

       and

       price < vwap

       and

      volume_now > avg_volume * 1.5
      and not bull_1h

    )



    if buy:

        return "BUY"



    elif sell:

        return "SELL"



    return "HOLD"

def ema_strategy(df, i):

    fast = df["Close"].rolling(10).mean()

    slow = df["Close"].rolling(20).mean()


    if fast.iloc[i] > slow.iloc[i]:

        return "BUY"


    return "SELL"

def ema_signal(df, i):

    fast = df["Close"].rolling(10).mean()

    slow = df["Close"].rolling(20).mean()


    if fast.iloc[i] > slow.iloc[i]:

        return "BUY"


    return "SELL"

def rsi_signal(df, i):

    delta = df["Close"].diff()


    gain = (

        delta.where(

            delta > 0,

            0

        )

    ).rolling(14).mean()


    loss = (

        -delta.where(

            delta < 0,

            0

        )

    ).rolling(14).mean()


    rs = gain / loss


    rsi = 100 - (

        100 / (1 + rs)

    )


    if rsi.iloc[i] < 30:

        return "BUY"


    return "SELL"
