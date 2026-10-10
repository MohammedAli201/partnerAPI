FROM python:3.12-slim
WORKDIR /app
COPY requirements-central.lock .
RUN pip install --no-cache-dir -r requirements-central.lock
COPY central central
RUN useradd --create-home payout
USER payout
EXPOSE 8001
CMD ["uvicorn", "central.app:app", "--host", "0.0.0.0", "--port", "8001"]
