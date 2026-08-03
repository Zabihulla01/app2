def split_data(

    df,

    train_ratio=0.7

):


    split = int(

        len(df)

        *

        train_ratio

    )



    train = (

        df

        .iloc[:split]

    )



    test = (

        df

        .iloc[split:]

    )



    return (

        train,

        test

    )
