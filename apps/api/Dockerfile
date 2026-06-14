FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY apps/api /app/apps/api
RUN pip install --no-cache-dir /app/apps/api

WORKDIR /app/apps/api
CMD ["sh", "-c", "uvicorn courtvision.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
