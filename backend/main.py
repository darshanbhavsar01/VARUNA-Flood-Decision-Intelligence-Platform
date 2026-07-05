"""VARUNA FastAPI app — single container serving API (+ built frontend later).

Run locally:  uvicorn backend.main:app --reload --port 8080
On Cloud Run:  uvicorn backend.main:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers import agents, citypulse, reports, risk
from .services.settings import get_settings, list_cities

REPO = Path(__file__).resolve().parents[1]
FRONTEND_DIST = REPO / "frontend" / "dist"

app = FastAPI(title="VARUNA", version="0.1.0",
              description="Flood Decision Intelligence Platform")

# Dev CORS (prod serves frontend from same origin, so this is harmless).
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

app.include_router(risk.router)
app.include_router(citypulse.router)
app.include_router(reports.router)
app.include_router(agents.router)


@app.get("/api/health")
def health():
    from .services import gemini
    s = get_settings()
    return {"status": "ok", "project": s.google_cloud_project or None,
            "dataset": s.bq_dataset, "gemini_configured": bool(s.gemini_api_key),
            "gemini_models": s.gemini_model_chain,
            "gemini_active_model": gemini.active_model()}


@app.get("/api/cities")
def cities():
    return {"cities": list_cities(), "default": get_settings().default_city}


# --- serve built frontend (present after `npm run build`); no-op if absent ---
if (FRONTEND_DIST / "index.html").exists():
    if (FRONTEND_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"),
                  name="assets")

    @app.get("/")
    def _index():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{path:path}")
    def _spa(path: str):
        # SPA fallback: serve a real file if it exists, else index.html
        f = FRONTEND_DIST / path
        return FileResponse(f if f.is_file() else FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    def _root():
        return {"service": "VARUNA", "frontend": "not built yet",
                "docs": "/docs", "health": "/api/health"}
