def market_trend(close1h):

    ema50 = (

        close1h

        .rolling(50)

        .mean()

    )


    ema200 = (

        close1h

        .rolling(200)

        .mean()

    )


    bull = (

    float(

        ema50.iloc[-1].item()

    )

    >

    float(

        ema200.iloc[-1].item()

    )
)


    return bull
