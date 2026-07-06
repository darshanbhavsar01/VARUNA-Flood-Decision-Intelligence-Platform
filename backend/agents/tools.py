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


def get_complaint_trend(ward_id: int, category_norm: str, date: str) -> dict:
    """Daily complaint counts for a ward and category in the ~10 days around `date`
    (YYYY-MM-DD). Use to see how sharp and sudden the spike was."""
    try:
        rows = bq.query(f"""
          SELECT FORMAT_DATE('%Y-%m-%d', DATE(created_at)) d, COUNT(*) n
          FROM {bq.t('grievances')}
          WHERE city_id='{CITY}' AND ward_id=@wid AND category_norm=@cat
            AND DATE(created_at) BETWEEN DATE_SUB(DATE(@d), INTERVAL 7 DAY)
                                     AND DATE_ADD(DATE(@d), INTERVAL 2 DAY)
          GROUP BY d ORDER BY d
        """, {"wid": ward_id, "cat": category_norm, "d": date})
        return {"trend": rows}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def get_rainfall_context(ward_id: int, date: str) -> dict:
    """Rainfall (mm) in the ward's zone on `date` and the two prior days. Use to judge
    whether rain explains the complaint spike, or whether citizens flagged it first."""
    try:
        rows = bq.query(f"""
          WITH gp AS (SELECT grid_point_id FROM {bq.t('ward_grid_map')}
                      WHERE ward_id=@wid LIMIT 1)
          SELECT FORMAT_DATE('%Y-%m-%d', DATE(ts)) d, ROUND(SUM(rain_mm),1) rain_mm
          FROM {bq.t('rainfall_hourly')}
          WHERE city_id='{CITY}' AND is_forecast=FALSE
            AND grid_point_id=(SELECT grid_point_id FROM gp)
            AND DATE(ts) BETWEEN DATE_SUB(DATE(@d), INTERVAL 2 DAY) AND DATE(@d)
          GROUP BY d ORDER BY d
        """, {"wid": ward_id, "d": date})
        return {"rainfall_by_day": rows}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def get_ward_profile(ward_id: int) -> dict:
    """Ward name, zone, whether low-lying, historical flood-prone spots, and current
    model risk band — to judge if this spike was in a ward the model already rated
    high, or one it rated only moderate (citizens catching it first)."""
    try:
        rows = bq.query(f"""
          WITH latest AS (
            SELECT ward_id, score FROM {bq.t('risk_scores')}
            WHERE city_id='{CITY}' AND horizon_hrs=24
              AND computed_at=(SELECT MAX(computed_at) FROM {bq.t('risk_scores')}
                               WHERE city_id='{CITY}' AND horizon_hrs=24))
          SELECT w.ward_name, w.zone, w.is_low_lying, w.historical_flood_count,
                 ROUND(l.score,3) risk_score
          FROM {bq.t('wards')} w LEFT JOIN latest l USING (ward_id)
          WHERE w.city_id='{CITY}' AND w.ward_id=@wid
        """, {"wid": ward_id})
        if not rows:
            return {"error": "ward not found"}
        r = rows[0]
        s = r["risk_score"]
        r["risk_band"] = ("high" if s and s >= 0.6 else "moderate" if s and s >= 0.3
                          else "low" if s is not None else "unknown")
        return r
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def get_zone_spike_comparison(ward_id: int, category_norm: str, date: str) -> dict:
    """Other wards in the SAME zone and their complaint counts for this category on
    `date` — to see whether neighbours corroborate a genuine local event."""
    try:
        rows = bq.query(f"""
          WITH z AS (SELECT zone FROM {bq.t('wards')}
                     WHERE city_id='{CITY}' AND ward_id=@wid)
          SELECT w.ward_name, COUNT(*) n
          FROM {bq.t('grievances')} g
          JOIN {bq.t('wards')} w ON w.city_id='{CITY}' AND w.ward_id=g.ward_id
          WHERE g.city_id='{CITY}' AND g.category_norm=@cat
            AND w.zone=(SELECT zone FROM z)
            AND DATE(g.created_at)=DATE(@d)
          GROUP BY w.ward_name ORDER BY n DESC LIMIT 8
        """, {"wid": ward_id, "cat": category_norm, "d": date})
        return {"same_zone_counts": rows}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


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
