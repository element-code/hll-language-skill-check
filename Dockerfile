FROM python:3.13-alpine

RUN apk add --no-cache \
    mtr \
    iputils \
    bash \
    ca-certificates \
    tzdata

WORKDIR /app

COPY ./requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "main"]