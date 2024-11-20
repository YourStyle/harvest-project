FROM python:3.9

WORKDIR /app

COPY parser_mock.py .
COPY ../.env .

RUN pip install -r requirements.txt

CMD ["python", "parser_mock.py"]