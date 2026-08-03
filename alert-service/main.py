from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()


# Allow frontend access
app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"]

)



@app.get(

"/alert/{stock}"

)

def alert(

stock:str

):


    try:


        response = requests.get(

        f"http://gateway:8000/analysis/{stock}"

        )


        data = response.json()



        prediction = (

        data["Prediction"]

        ["Prediction"]

        )



        confidence = (

        data["Confidence"]

        ["Confidence"]

        )



        signal = "HOLD"



        if(

        prediction=="BUY"

        and

        confidence>=80

        ):

            signal = "STRONG BUY"



        elif(

        prediction=="SELL"

        and

        confidence>=80

        ):

            signal = "STRONG SELL"



        return {

            "Alert":

            signal,


            "Data":{

                "Signal":

                signal,


                "Confidence":

                confidence,


                "Analysis":

                data

            }

        }



    except Exception as e:


        return {

            "error":

            str(

            e

            )

        }
