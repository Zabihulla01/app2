def optimize_stock(

    backtest,

    stock

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

                        "adx":

                        adx,


                        "hold":

                        hold,


                        "rr":

                        rr,


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
