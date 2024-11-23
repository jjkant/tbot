# Dockerfile for Eligibility Processor Service

FROM python:3.9-slim

WORKDIR /app

COPY eligibility_processor.py /app
COPY requirements.txt /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "eligibility_processor.py"]
