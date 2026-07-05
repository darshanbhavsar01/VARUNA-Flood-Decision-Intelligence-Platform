# Deploy — Cloud Run (asia-south1, scale-to-zero, budget-safe §6)

**Live:** https://varuna-229692962627.asia-south1.run.app

## One command
```bash
# from repo root; GEMINI_API_KEY + GEMINI_MODELS come from your .env.
# NOTE the ^##^ custom delimiter: GEMINI_MODELS contains commas, so we can't use
# the default comma-separated --set-env-vars form.
set -a; source .env; set +a
gcloud run deploy varuna --source . \
  --project=main-aura-398409 --region=asia-south1 \
  --allow-unauthenticated --min-instances=0 --memory=512Mi --timeout=120 --quiet \
  --set-env-vars="^##^GEMINI_API_KEY=${GEMINI_API_KEY}##GEMINI_MODELS=${GEMINI_MODELS}##GOOGLE_CLOUD_PROJECT=main-aura-398409##BQ_DATASET=varuna##BQ_LOCATION=asia-south1"
```

**Gemini quota resilience:** `GEMINI_MODELS` is an ordered fallback chain. Each
model has its own free-tier quota bucket, so when one returns 429 the app advances
to the next (and skips 404s for models that don't exist yet). `/api/health` shows
the chain and the currently-active model.

## How it fits together
- **One container** (`Dockerfile`) serves the FastAPI API and the built frontend
  (`frontend/dist/`). `.dockerignore` keeps the image lean; `.gcloudignore` controls
  the Cloud Build upload (must NOT exclude `frontend/dist/`, which `.gitignore` does).
- **Auth:** the Cloud Run runtime service account (`…-compute@…`, has `roles/editor`)
  provides ADC for BigQuery + Firestore. No key files in the image.
- **Secrets:** `GEMINI_API_KEY` is injected as an env var (§6), never baked in.
- **Cost controls:** `min-instances=0` (scale to zero), 512Mi, AI-Studio Gemini (not
  Vertex endpoints), BigQuery/Firestore/Cloud Run all within free tier. Budget alert
  set at ₹500/₹900/₹1000 on a ₹1000 cap.

## Notes / gotchas
- `frontend/dist/` is gitignored (build artifact). A clone must build the frontend
  (or keep the placeholder) before deploying, or the `COPY frontend/dist/` step fails.
- First deploy auto-creates the `cloud-run-source-deploy` Artifact Registry repo.
- Enabled APIs: run, cloudbuild, artifactregistry, bigquery, firestore, billingbudgets.
