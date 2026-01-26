FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=8080

ARG REQUIREMENTS=requirements.dashboard.txt

WORKDIR /app

COPY ${REQUIREMENTS} requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY schemas ./schemas
COPY schema.sql schema.postgres.sql ./
COPY config ./config

EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn src.dashboard_api:app --host 0.0.0.0 --port ${PORT:-8080}"]
