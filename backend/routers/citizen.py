"""Citizen View endpoints (§3 Persona B, §4 P1 #10):
  - locate:   lat/lng -> the citizen's ward (point-in-polygon)
  - advisory: a short, grounded safety advisory for a ward from its current risk
  - ask:      a natural-language question answered from the ward's risk + rainfall

All LLM calls are grounded on real risk-model output and degrade gracefully.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services import bq, gemini
from ..services.settings import get_settings

router = APIRouter(prefix="/api/citizen", tags=["citizen"])


def _band(s):
    if s is None:
        return "unknown"
    return "high" if s >= 0.6 else "moderate" if s >= 0.3 else "low"


def _ward_context(city: str, ward_id: int) -> dict | None:
    rows = bq.query(f"""
      WITH latest AS (
        SELECT ward_id, score, top_features FROM {bq.t('risk_scores')}
        WHERE city_id=@city AND horizon_hrs=24
          AND computed_at=(SELECT MAX(computed_at) FROM {bq.t('risk_scores')}
                           WHERE city_id=@city AND horizon_hrs=24)
      )
      SELECT w.ward_id, w.ward_name, w.zone, w.is_low_lying,
             w.historical_flood_count, l.score, l.top_features
      FROM {bq.t('wards')} w LEFT JOIN latest l USING (ward_id)
      WHERE w.city_id=@city AND w.ward_id=@wid
    """, {"city": city, "wid": ward_id})
    if not rows:
        return None
    r = rows[0]
    tf = r["top_features"]
    if isinstance(tf, (str, bytes)):
        tf = json.loads(tf)
    return {"ward_id": r["ward_id"], "ward_name": r["ward_name"], "zone": r["zone"],
            "is_low_lying": r["is_low_lying"],
            "historical_flood_count": r["historical_flood_count"],
            "risk_score": r["score"], "risk_band": _band(r["score"]),
            "top_features": tf or []}


def _recent_rain(city: str) -> dict:
    rows = bq.query(f"""
      WITH mx AS (SELECT MAX(ts) m FROM {bq.t('rainfall_hourly')}
                  WHERE city_id=@city AND is_forecast=FALSE)
      SELECT ROUND(SUM(IF(ts>TIMESTAMP_SUB((SELECT m FROM mx),INTERVAL 24 HOUR),
                          rain_mm,0)),1) AS rain_24h,
             ROUND(SUM(IF(ts>TIMESTAMP_SUB((SELECT m FROM mx),INTERVAL 72 HOUR),
                          rain_mm,0)),1) AS rain_72h
      FROM {bq.t('rainfall_hourly')}
      WHERE city_id=@city AND is_forecast=FALSE
        AND ts>TIMESTAMP_SUB((SELECT m FROM mx),INTERVAL 72 HOUR)
    """, {"city": city})
    return rows[0] if rows else {"rain_24h": None, "rain_72h": None}


@router.get("/locate")
def locate(lat: float, lng: float, city: str = Query(None)):
    """Return the ward containing a lat/lng (for 'use my location')."""
    city = city or get_settings().default_city
    rows = bq.query(f"""
      SELECT ward_id, ward_name, zone FROM {bq.t('wards')}
      WHERE city_id=@city AND ST_CONTAINS(geometry, ST_GEOGPOINT(@lng,@lat))
      LIMIT 1
    """, {"city": city, "lat": lat, "lng": lng})
    if not rows:
        raise HTTPException(404, "No ward found for that location (outside Bengaluru?)")
    return rows[0]


@router.get("/advisory")
def advisory(ward_id: int, city: str = Query(None)):
    """A short, grounded safety advisory for a ward based on its current risk."""
    city = city or get_settings().default_city
    ctx = _ward_context(city, ward_id)
    if not ctx:
        raise HTTPException(404, f"Ward {ward_id} not found")
    band = ctx["risk_band"]
    fallback = {
        "high": "High flood risk in your ward. Avoid low-lying roads and underpasses, "
                "don't wade through standing water, keep emergency numbers handy, and "
                "move vehicles to higher ground.",
        "moderate": "Moderate flood risk. Stay alert to rainfall, avoid known "
                    "waterlogging spots, and don't park in low-lying areas.",
        "low": "Low flood risk right now. Stay aware during heavy rain and report any "
               "waterlogging you see.",
        "unknown": "Risk data is unavailable for your ward right now. Stay cautious "
                   "during heavy rain.",
    }[band]
    try:
        prompt = (
            f"Ward: {ctx['ward_name']} ({ctx['zone']} zone), Bengaluru. "
            f"Flood risk: {band} ({'%.0f%%' % (ctx['risk_score']*100) if ctx['risk_score'] is not None else 'n/a'}). "
            f"Low-lying: {ctx['is_low_lying']}. Historical flood-prone spots: "
            f"{ctx['historical_flood_count']}. "
            "Write a concise safety advisory (<=45 words) for residents, in plain, "
            "calm language. No preamble.")
        text = gemini.generate(prompt, temperature=0.3)
    except gemini.GeminiError:
        text = fallback
    return {**ctx, "advisory": text}


class AskIn(BaseModel):
    ward_id: int
    question: str
    city: str | None = None


@router.post("/ask")
def ask(body: AskIn):
    """Answer a resident's flooding question, grounded in the ward's risk + rainfall."""
    city = body.city or get_settings().default_city
    ctx = _ward_context(city, body.ward_id)
    if not ctx:
        raise HTTPException(404, f"Ward {body.ward_id} not found")
    rain = _recent_rain(city)
    feats = ", ".join(f"{f.get('feature')}={f.get('attribution')}"
                      for f in (ctx["top_features"] or [])[:4])
    try:
        prompt = (
            f"You are VARUNA's citizen assistant for Bengaluru urban flooding. Answer "
            f"the resident's question factually and calmly using ONLY this grounding:\n"
            f"- Ward: {ctx['ward_name']} ({ctx['zone']} zone)\n"
            f"- Current flood risk: {ctx['risk_band']} "
            f"({'%.0f%%' % (ctx['risk_score']*100) if ctx['risk_score'] is not None else 'n/a'})\n"
            f"- Low-lying: {ctx['is_low_lying']}; flood-prone spots nearby: "
            f"{ctx['historical_flood_count']}\n"
            f"- Recent rainfall: {rain.get('rain_24h')} mm (24h), {rain.get('rain_72h')} mm (72h)\n"
            f"- Top risk drivers: {feats}\n\n"
            f"Question: {body.question}\n\n"
            "Answer in <=4 sentences. Be honest this is complaint-verified waterlogging "
            "risk, not a guaranteed forecast. If asked about a different area, say you "
            "can only speak to this ward.")
        answer = gemini.generate(prompt, temperature=0.3)
        ok = True
    except gemini.GeminiRateLimited:
        answer = ("The assistant is momentarily rate-limited. Meanwhile: your ward's "
                  f"current flood risk is {ctx['risk_band']}.")
        ok = False
    except gemini.GeminiError:
        answer = f"Your ward's current flood risk is {ctx['risk_band']}."
        ok = False
    return {"ok": ok, "ward": {"ward_id": ctx["ward_id"], "ward_name": ctx["ward_name"],
                               "zone": ctx["zone"], "risk_band": ctx["risk_band"],
                               "risk_score": ctx["risk_score"]},
            "answer": answer, "model": gemini.active_model()}
