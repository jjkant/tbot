# Dockerfile for Message Poller Service

FROM python:3.9-slim

WORKDIR /app

COPY event_poller.py /app
COPY requirements.txt /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "event_poller.py"]
