FROM python:3-alpine

WORKDIR /app

COPY . /app
RUN apk add --no-cache alpine-sdk libffi-dev openssl-dev && \
    pip install -r requirements.txt

ENTRYPOINT ["python", "/app/main.py"]