FROM python:3.9

WORKDIR /app

COPY bot.py .
COPY ../.env .

RUN pip install -r requirements.txt

CMD ["python", "bot.py"]