FROM python:3-alpine

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN apk add --no-cache alpine-sdk libffi-dev openssl-dev && \
    pip install -r requirements.txt

COPY . /app

ENTRYPOINT ["python", "/app/main.py"]