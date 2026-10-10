FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

# System deps (optional but useful for psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-payout.lock /app/requirements-payout.lock
RUN pip install --no-cache-dir -r /app/requirements-payout.lock

COPY . /app
COPY --from=frontend /build/static/hubaal-react /app/static/hubaal-react

# Fly uses 8080 by default in many templates; we'll listen on 8080
EXPOSE 8080

# Production server: gunicorn + uvicorn worker
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
