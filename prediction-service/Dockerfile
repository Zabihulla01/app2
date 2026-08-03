FROM python:3.9-slim

WORKDIR /app

COPY . .

RUN pip install fastapi uvicorn requests pandas yfinance xgboost ta scikit-learn

CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8004"]
