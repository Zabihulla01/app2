def calculate_profit(

    move,

    atr,

    rr

):


    move = float(

        move

    )



    atr = float(

        atr

    )



    rr = float(

        rr

    )



    target = (

        rr *

        atr

    )



    stop = atr



    if move >= target:


        return (

            move

            /

            atr

        )



    elif move <= -stop:


        return -1



    else:


        return (

            move

            /

            atr

        )

