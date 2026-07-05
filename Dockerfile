# VARUNA — single container: FastAPI API (+ built frontend when present).
# Cloud Run, region asia-south1, scale-to-zero. Uses the runtime service account
# for BigQuery/Firestore (ADC); GEMINI_API_KEY is injected as an env var at deploy.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# app code + city configs (settings.py reads configs/<city>.yaml)
COPY backend/ ./backend/
COPY configs/ ./configs/
# built frontend if present (created by `npm run build`); harmless if empty
COPY frontend/dist/ ./frontend/dist/

EXPOSE 8080
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
