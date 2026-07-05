"""Risk endpoints — the data behind Command View's map + explainability panel (P0).

All read-only over BigQuery `risk_scores` + `wards`. No LLM, no new credentials.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from ..services import bq
from ..services.settings import get_city_config, get_settings

router = APIRouter(prefix="/api/risk", tags=["risk"])


def _latest_scores_cte(city: str, horizon: int) -> tuple[str, dict]:
    """CTE selecting the most recent risk snapshot for a city+horizon."""
    sql = f"""
      SELECT ward_id, score, top_features, computed_at,
             RANK() OVER (ORDER BY score DESC) AS risk_rank
      FROM {bq.t('risk_scores')}
      WHERE city_id=@city AND horizon_hrs=@h
        AND computed_at = (SELECT MAX(computed_at) FROM {bq.t('risk_scores')}
                           WHERE city_id=@city AND horizon_hrs=@h)
    """
    return sql, {"city": city, "h": horizon}


def _as_json(v):
    """BQ JSON columns arrive already parsed; JSON strings need decoding."""
    if v is None:
        return None
    return json.loads(v) if isinstance(v, (str, bytes, bytearray)) else v


def _risk_band(score) -> str:
    if score is None:
        return "unknown"
    if score >= 0.6:
        return "high"
    if score >= 0.3:
        return "moderate"
    return "low"


@router.get("/wards.geojson")
def wards_geojson(city: str = Query(None), horizon: int = 24):
    """Ward polygons + latest risk merged -> the choropleth source (FeatureCollection)."""
    city = city or get_settings().default_city
    latest, params = _latest_scores_cte(city, horizon)
    params["h"] = horizon
    rows = bq.query(f"""
      WITH latest AS ({latest})
      SELECT w.ward_id, w.ward_name, w.zone, w.is_low_lying,
             w.historical_flood_count,
             ST_ASGEOJSON(w.geometry) AS geom,
             l.score, l.risk_rank, l.top_features,
             FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', l.computed_at) AS computed_at
      FROM {bq.t('wards')} w
      LEFT JOIN latest l USING (ward_id)
      WHERE w.city_id=@city
      ORDER BY w.ward_id
    """, params)
    if not rows:
        raise HTTPException(404, f"No wards for city '{city}'")

    features = []
    for r in rows:
        score = r["score"]
        features.append({
            "type": "Feature",
            "geometry": json.loads(r["geom"]) if r["geom"] else None,
            "properties": {
                "ward_id": r["ward_id"], "ward_name": r["ward_name"],
                "zone": r["zone"], "is_low_lying": r["is_low_lying"],
                "historical_flood_count": r["historical_flood_count"],
                "risk_score": round(score, 4) if score is not None else None,
                "risk_rank": r["risk_rank"], "risk_band": _risk_band(score),
                "top_features": _as_json(r["top_features"]),
            },
        })
    computed = next((r["computed_at"] for r in rows if r["computed_at"]), None)
    return {"type": "FeatureCollection", "city_id": city,
            "horizon_hrs": horizon, "computed_at": computed, "features": features}


@router.get("/wards")
def wards_ranked(city: str = Query(None), horizon: int = 24,
                 limit: int = 200):
    """Ranked ward list for the risk table / feed (no geometry)."""
    city = city or get_settings().default_city
    latest, params = _latest_scores_cte(city, horizon)
    params["h"] = horizon
    params["lim"] = limit
    rows = bq.query(f"""
      WITH latest AS ({latest})
      SELECT w.ward_id, w.ward_name, w.zone, w.is_low_lying,
             w.historical_flood_count, l.score, l.risk_rank
      FROM {bq.t('wards')} w
      LEFT JOIN latest l USING (ward_id)
      WHERE w.city_id=@city
      ORDER BY l.score DESC NULLS LAST, w.ward_id
      LIMIT @lim
    """, params)
    for r in rows:
        r["risk_score"] = round(r.pop("score"), 4) if r["score"] is not None else None
        r["risk_band"] = _risk_band(r["risk_score"])
    return {"city_id": city, "horizon_hrs": horizon, "wards": rows}


@router.get("/ward/{ward_id}")
def ward_detail(ward_id: int, city: str = Query(None), horizon: int = 24):
    """One ward: metadata + risk + explanation attributions."""
    city = city or get_settings().default_city
    latest, params = _latest_scores_cte(city, horizon)
    params.update({"h": horizon, "wid": ward_id})
    rows = bq.query(f"""
      WITH latest AS ({latest})
      SELECT w.ward_id, w.ward_name, w.zone, w.is_low_lying,
             w.historical_flood_count, l.score, l.risk_rank, l.top_features,
             FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', l.computed_at) AS computed_at
      FROM {bq.t('wards')} w
      LEFT JOIN latest l USING (ward_id)
      WHERE w.city_id=@city AND w.ward_id=@wid
    """, params)
    if not rows:
        raise HTTPException(404, f"Ward {ward_id} not found in city '{city}'")
    r = rows[0]
    score = r["score"]
    return {
        "ward_id": r["ward_id"], "ward_name": r["ward_name"], "zone": r["zone"],
        "is_low_lying": r["is_low_lying"],
        "historical_flood_count": r["historical_flood_count"],
        "risk_score": round(score, 4) if score is not None else None,
        "risk_rank": r["risk_rank"], "risk_band": _risk_band(score),
        "computed_at": r["computed_at"],
        "top_features": _as_json(r["top_features"]) or [],
    }


@router.get("/summary")
def summary(city: str = Query(None), horizon: int = 24):
    """Situation snapshot for the header: counts by band + top wards."""
    city = city or get_settings().default_city
    latest, params = _latest_scores_cte(city, horizon)
    params["h"] = horizon
    rows = bq.query(f"""
      WITH latest AS ({latest})
      SELECT w.ward_id, w.ward_name, w.zone, l.score,
             FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', l.computed_at) AS computed_at
      FROM {bq.t('wards')} w LEFT JOIN latest l USING (ward_id)
      WHERE w.city_id=@city
    """, params)
    bands = {"high": 0, "moderate": 0, "low": 0, "unknown": 0}
    for r in rows:
        bands[_risk_band(r["score"])] += 1
    top = sorted([r for r in rows if r["score"] is not None],
                 key=lambda r: r["score"], reverse=True)[:5]
    return {
        "city_id": city, "horizon_hrs": horizon, "total_wards": len(rows),
        "bands": bands,
        "computed_at": next((r["computed_at"] for r in rows if r["computed_at"]), None),
        "top_wards": [{"ward_id": r["ward_id"], "ward_name": r["ward_name"],
                       "zone": r["zone"], "risk_score": round(r["score"], 4)}
                      for r in top],
    }
