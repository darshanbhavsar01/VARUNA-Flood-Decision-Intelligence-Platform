# VARUNA — single container: FastAPI API + built React frontend.
# Cloud Run, region asia-south1, scale-to-zero. Runtime service account provides
# ADC for BigQuery/Firestore; GEMINI_API_KEY is injected as an env var at deploy.

# --- stage 1: build the frontend ---
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build            # -> /fe/dist

# --- stage 2: python runtime ---
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY configs/ ./configs/
COPY --from=frontend /fe/dist ./frontend/dist

EXPOSE 8080
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
