# API image — FastAPI, lightweight (no document libs; it only dispatches jobs
# and serves files from the shared jobs volume).
# Build context = repo root:
#   docker build -f DsideOS/api/Dockerfile -t dsideos-api .
FROM python:3.12-slim

WORKDIR /app

COPY DsideOS/api/requirements.txt /app/api-requirements.txt
RUN pip install --no-cache-dir -r /app/api-requirements.txt

COPY DsideOS/ /app/DsideOS/

ENV PYTHONPATH=/app/DsideOS
WORKDIR /app/DsideOS

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
