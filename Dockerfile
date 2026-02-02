FROM python:3.12-slim

WORKDIR /app

# System deps (optional but useful for psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Fly uses 8080 by default in many templates; we'll listen on 8080
EXPOSE 8080

# Production server: gunicorn + uvicorn worker
CMD ["gunicorn", "main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080", "--workers", "2"]
