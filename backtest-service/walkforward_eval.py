from walkforward import walkforward_split

from indicators import add_indicators

from market_filter import market_trend

from strategy import generate_signal

from risk import calculate_profit

from scoring import risk_score

import numpy as np

import yfinance as yf



def evaluate(

    df,

    stock,

    adx_min,

    hold,

    target_rr

):


    splits = walkforward_split(

        df

    )


    results=[]



    for i,(

        train,

        test

    ) in enumerate(

        splits

    ):



        test = add_indicators(

            test

        )



        df1h = yf.download(

            stock,

            period="60d",

            interval="1h",

            auto_adjust=True

        )



        bull = market_trend(

            df1h["Close"]

            .squeeze()

        )



        wins=0

        losses=0

        gp=0

        gl=0

        returns=[]



        for j in range(

            50,

            len(

                test

            )-hold

        ):



            signal = generate_signal(

                test,

                j,

                adx_min,

                bull

            )



            if signal=="HOLD":

                continue



            current=float(

                test["Close"]

                .iloc[j]

            )



            future=float(

                test["Close"]

                .iloc[j+hold]

            )



            move=(

                future-current

            ) if signal=="BUY" else (

                current-future

            )



            profit=calculate_profit(

                move,

                test["ATR"]

                .iloc[j],

                target_rr

            )



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

        pf=(gp/gl) if gl else 0



        sharpe=(

            np.mean(

                returns

            )

            /

            np.std(

                returns

            )

        ) if (

            len(

                returns

            )>1

        ) else 0



        maxdd=0



        if len(

            returns

        ):


            cum=np.cumsum(

                returns

            )


            peak=np.maximum.accumulate(

                cum

            )


            maxdd=np.max(

                peak-cum

            )



        results.append(

            {

                "Window":

                i+1,


                "Train":

                len(

                    train

                ),


                "Test":

                len(

                    test

                ),


                "Trades":

                total,


                "PF":

                round(

                    pf,

                    2

                ),


                "Sharpe":

                round(

                    sharpe,

                    2

                ),


                "RiskScore":

                round(

                    risk_score(

                        pf,

                        sharpe,

                        maxdd

                    ),

                    2

                )

            }

        )



    return results
