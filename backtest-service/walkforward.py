def walkforward_split(

    df,

    train_ratio=0.5,

    windows=3

):


    splits=[]


    size=len(

        df

    )


    step=(

        size

        //

        (

            windows

            +

            1

        )

    )



    for i in range(

        1,

        windows+1

    ):


        train=df.iloc[

            :

            i*step

        ]



        test=df.iloc[

            i*step:

            (

                i+1

            )

            *

            step

        ]



        if (

            len(

                train

            )

            >200

            and

            len(

                test

            )

            >50

        ):


            splits.append(

                (

                    train,

                    test

                )

            )


    return splits
