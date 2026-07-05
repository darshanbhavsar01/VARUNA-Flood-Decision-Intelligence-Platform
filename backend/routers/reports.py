"""Citizen photo-report flow (§4 P0 #5): upload photo -> Gemini Vision severity
-> Firestore -> appears live on the Command View map.

POST /api/reports   (multipart: image, [lat], [lng], [ward_id], [note], [city])
GET  /api/reports   -> recent reports for the map overlay

Privacy/cost note: we store the Vision *analysis*, not the raw image (no Cloud
Storage needed, keeps within budget §6).
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from ..services import bq, firestore, gemini
from ..services.settings import get_settings

router = APIRouter(prefix="/api/reports", tags=["reports"])

MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
CATEGORIES = ["WATERLOGGING", "DRAINAGE", "GARBAGE", "ROADS", "OTHER"]
SEVERITIES = ["low", "moderate", "high", "severe"]

VISION_PROMPT = f"""
You are triaging a citizen-submitted photo of a possible urban civic/flood issue in
Bengaluru. Analyze ONLY what is visible. Return strict JSON:
{{
  "flood_related": boolean,
  "category_norm": one of {CATEGORIES},
  "severity": one of {SEVERITIES},
  "water_depth_estimate_cm": integer or null (visible standing-water depth),
  "summary": "one factual sentence describing what is shown",
  "hazards": ["short", "notable", "hazards"]
}}
If no water is visible, water_depth_estimate_cm = null and flood_related likely false.
Be conservative; do not invent details not visible in the image.
""".strip()


def _resolve_ward(city_id: str, lat: float, lng: float) -> dict | None:
    rows = bq.query(f"""
      SELECT ward_id, ward_name, zone
      FROM {bq.t('wards')}
      WHERE city_id=@city AND ST_CONTAINS(geometry, ST_GEOGPOINT(@lng,@lat))
      LIMIT 1
    """, {"city": city_id, "lat": lat, "lng": lng})
    return rows[0] if rows else None


def _clean_analysis(a: dict) -> dict:
    cat = str(a.get("category_norm", "OTHER")).upper()
    sev = str(a.get("severity", "low")).lower()
    depth = a.get("water_depth_estimate_cm")
    try:
        depth = int(depth) if depth is not None else None
    except (TypeError, ValueError):
        depth = None
    return {
        "flood_related": bool(a.get("flood_related", False)),
        "category_norm": cat if cat in CATEGORIES else "OTHER",
        "severity": sev if sev in SEVERITIES else "low",
        "water_depth_estimate_cm": depth,
        "summary": str(a.get("summary", ""))[:400],
        "hazards": [str(h)[:60] for h in (a.get("hazards") or [])][:6],
    }


@router.post("")
async def create_report(
    image: UploadFile = File(...),
    lat: float | None = Form(None),
    lng: float | None = Form(None),
    ward_id: int | None = Form(None),
    note: str | None = Form(None),
    city: str | None = Form(None),
):
    city_id = city or get_settings().default_city
    mime = (image.content_type or "").lower()
    if mime not in ALLOWED_MIME:
        raise HTTPException(415, f"Unsupported image type '{mime}'")
    data = await image.read()
    if not data:
        raise HTTPException(400, "empty image")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "image too large (max 8MB)")

    # Gemini Vision — degrade gracefully to an 'unanalyzed' report if it fails.
    try:
        analysis = _clean_analysis(gemini.analyze_image(data, mime, VISION_PROMPT))
        analysis_ok = True
    except gemini.GeminiError:
        analysis = {"flood_related": None, "category_norm": "OTHER",
                    "severity": "low", "water_depth_estimate_cm": None,
                    "summary": "(vision analysis unavailable)", "hazards": []}
        analysis_ok = False

    # ward resolution: explicit ward_id wins; else derive from lat/lng.
    ward = None
    if ward_id is None and lat is not None and lng is not None:
        try:
            ward = _resolve_ward(city_id, lat, lng)
        except Exception:  # noqa: BLE001 — geo lookup is best-effort
            ward = None
    resolved_ward_id = ward_id if ward_id is not None else (ward or {}).get("ward_id")

    doc = {
        "city_id": city_id,
        "ward_id": resolved_ward_id,
        "ward_name": (ward or {}).get("ward_name"),
        "zone": (ward or {}).get("zone"),
        "lat": lat, "lng": lng,
        "note": (note or "")[:500],
        "source": "citizen",
        "status": "new",
        "analysis_ok": analysis_ok,
        **{f"analysis_{k}": v for k, v in analysis.items()},
    }
    try:
        saved = firestore.add_report(doc)
    except firestore.FirestoreError as e:
        raise HTTPException(503, f"report store unavailable: {e}")
    return {"ok": True, "report": saved}


@router.get("")
def list_reports(city: str = Query(None), limit: int = 100):
    city_id = city or get_settings().default_city
    try:
        return {"city_id": city_id, "reports": firestore.list_reports(city_id, limit)}
    except firestore.FirestoreError as e:
        raise HTTPException(503, f"report store unavailable: {e}")
