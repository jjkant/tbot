# Dockerfile for Action Handler Service

FROM python:3.9-slim

WORKDIR /app

COPY action_handler.py /app
COPY requirements.txt /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "action_handler.py"]
