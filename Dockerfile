# Hugging Face Spaces Docker deployment for MindGuard.
# Builds the Vite frontend, then serves it from FastAPI on port 7860.

FROM node:20-alpine AS frontend

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir gunicorn -r requirements.txt

COPY backend/ /app/backend/
COPY scraper_worker.py /app/scraper_worker.py
COPY --from=frontend /app/dist /app/frontend

ENV FRONTEND_DIR=/app/frontend
ENV PYTHONPATH=/app
ENV API_HOST=0.0.0.0
ENV API_PORT=7860
ENV HF_CACHE_DIR=/tmp/huggingface

EXPOSE 7860

CMD gunicorn backend.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers 1 \
    --bind 0.0.0.0:${PORT:-7860} \
    --timeout 180 \
    --keep-alive 5 \
    --log-level info
