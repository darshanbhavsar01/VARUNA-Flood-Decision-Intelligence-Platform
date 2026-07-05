"""Tools exposed to the ADK agents (§9). Each is a plain function with a clear
docstring — ADK turns these into callable tools the LLM can invoke, and the UI
shows which tools fired (visible agency).

All read the live BigQuery data or the SOP RAG index. The resource inventory is
clearly labeled SIMULATED (§13 — no fabricated data passed off as real).
"""
from __future__ import annotations

from ..services import bq
from ..services.settings import get_settings
from . import sop_rag

CITY = "blr"


def _latest_scores_sql():
    return f"""
      WITH latest AS (
        SELECT ward_id, score,
               RANK() OVER (ORDER BY score DESC) rk
        FROM {bq.t('risk_scores')}
        WHERE city_id='{CITY}' AND horizon_hrs=24
          AND computed_at=(SELECT MAX(computed_at) FROM {bq.t('risk_scores')}
                           WHERE city_id='{CITY}' AND horizon_hrs=24)
      )
      SELECT w.ward_id, w.ward_name, w.zone, w.is_low_lying,
             w.historical_flood_count, l.score, l.rk
      FROM {bq.t('wards')} w JOIN latest l USING (ward_id)
      WHERE w.city_id='{CITY}'
    """


def get_risk_assessment(top_n: int = 8) -> dict:
    """Return the current ward-level flood-risk snapshot: how many wards are High/
    Moderate/Low risk and the top_n highest-risk wards (name, zone, score, whether
    low-lying, historical flood-prone spots). Use this to know which wards need action."""
    try:
        rows = bq.query(_latest_scores_sql() + " ORDER BY l.score DESC")
        if not rows:
            return {"error": "no risk scores available"}
        bands = {"high": 0, "moderate": 0, "low": 0}
        for r in rows:
            s = r["score"]
            bands["high" if s >= 0.6 else "moderate" if s >= 0.3 else "low"] += 1
        top = [{"ward_name": r["ward_name"], "zone": r["zone"],
                "risk_score": round(r["score"], 3),
                "is_low_lying": r["is_low_lying"],
                "historical_flood_spots": r["historical_flood_count"]}
               for r in rows[:top_n]]
        return {"total_wards": len(rows), "bands": bands, "top_wards": top}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def get_rainfall_outlook() -> dict:
    """Return a recent rainfall summary per BBMP zone (total mm over the last 24h and
    72h in the available data window). Use this to judge how much rain is driving risk."""
    try:
        rows = bq.query(f"""
          WITH mx AS (SELECT MAX(ts) m FROM {bq.t('rainfall_hourly')}
                      WHERE city_id='{CITY}' AND is_forecast=FALSE)
          SELECT grid_point_id AS zone,
                 ROUND(SUM(IF(ts > TIMESTAMP_SUB((SELECT m FROM mx), INTERVAL 24 HOUR),
                             rain_mm, 0)),1) AS rain_24h_mm,
                 ROUND(SUM(IF(ts > TIMESTAMP_SUB((SELECT m FROM mx), INTERVAL 72 HOUR),
                             rain_mm, 0)),1) AS rain_72h_mm
          FROM {bq.t('rainfall_hourly')}
          WHERE city_id='{CITY}' AND is_forecast=FALSE
            AND ts > TIMESTAMP_SUB((SELECT m FROM mx), INTERVAL 72 HOUR)
          GROUP BY zone ORDER BY rain_72h_mm DESC
        """)
        return {"zones": rows, "note": "actuals from the latest available window"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def search_sops(query: str) -> dict:
    """Search official disaster-management SOP/guideline documents (NDMA, MoHUA) for
    passages relevant to `query`. Returns the top passages with their source citation
    and page. ALWAYS use this to ground each recommended action in an official SOP,
    and cite the returned `cite` + `page` for every action."""
    try:
        if not sop_rag.available():
            return {"error": "SOP index not available", "passages": []}
        hits = sop_rag.search(query, k=4)
        return {"passages": [{"cite": h["cite"], "page": h["page"],
                              "text": h["text"][:600], "score": h["score"]}
                             for h in hits]}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200], "passages": []}


def get_resource_inventory(zone: str = "") -> dict:
    """Return the available emergency resources (dewatering pumps, crews, boats,
    relief shelters) for a BBMP zone, to allocate in the response plan. NOTE: this
    inventory is SIMULATED demo data, not a live feed."""
    # Clearly-labeled simulated inventory (§13).
    base = {
        "East": {"pumps": 6, "crews": 4, "boats": 1, "shelters": 3},
        "West": {"pumps": 5, "crews": 4, "boats": 1, "shelters": 3},
        "South": {"pumps": 5, "crews": 3, "boats": 1, "shelters": 2},
        "Mahadevapura": {"pumps": 4, "crews": 3, "boats": 2, "shelters": 2},
        "Bommanahalli": {"pumps": 4, "crews": 3, "boats": 2, "shelters": 2},
        "Yelahanka": {"pumps": 3, "crews": 2, "boats": 1, "shelters": 2},
        "Dasarahalli": {"pumps": 2, "crews": 2, "boats": 0, "shelters": 1},
        "Rajarajeswari Nagar": {"pumps": 3, "crews": 2, "boats": 1, "shelters": 2},
    }
    if zone and zone in base:
        return {"zone": zone, "resources": base[zone], "simulated": True}
    return {"zones": base, "simulated": True}
