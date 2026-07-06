"""Anomaly feed (§3, §8b): proactive alerts where a ward's flood-signal complaints
spiked far above its seasonal baseline — the 'citizens as sensors' early-warning.

Each alert carries context: the ward's current model risk band (to surface cases the
rain model rated only moderate) and the rainfall that day, so the Insight Agent and
the UI can tell the story.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..services import bq
from ..services.settings import get_settings

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


def _band(s):
    if s is None:
        return "unknown"
    return "high" if s >= 0.6 else "moderate" if s >= 0.3 else "low"


@router.get("")
def feed(city: str = Query(None), limit: int = 30, order: str = "severity"):
    """Anomaly feed. order=severity (biggest spikes) | recent (latest first)."""
    city = city or get_settings().default_city
    order_sql = "a.ts DESC, a.deviation DESC" if order == "recent" \
        else "a.deviation DESC, a.observed DESC"
    rows = bq.query(f"""
      WITH latest AS (
        SELECT ward_id, score FROM {bq.t('risk_scores')}
        WHERE city_id=@city AND horizon_hrs=24
          AND computed_at=(SELECT MAX(computed_at) FROM {bq.t('risk_scores')}
                           WHERE city_id=@city AND horizon_hrs=24)
      ),
      rain AS (
        SELECT m.ward_id, DATE(r.ts) d, SUM(r.rain_mm) mm
        FROM {bq.t('rainfall_hourly')} r
        JOIN {bq.t('ward_grid_map')} m USING (grid_point_id)
        WHERE r.city_id=@city AND r.is_forecast=FALSE
        GROUP BY m.ward_id, d
      )
      SELECT a.ward_id, w.ward_name, w.zone, a.category_norm,
             FORMAT_TIMESTAMP('%Y-%m-%d', a.ts) AS date,
             a.observed, a.expected, a.deviation,
             l.score AS risk_score,
             ROUND(IFNULL(rn.mm, 0), 1) AS rain_mm_that_day
      FROM {bq.t('anomalies')} a
      JOIN {bq.t('wards')} w ON w.city_id=@city AND w.ward_id=a.ward_id
      LEFT JOIN latest l ON l.ward_id=a.ward_id
      LEFT JOIN rain rn ON rn.ward_id=a.ward_id AND rn.d=DATE(a.ts)
      WHERE a.city_id=@city
      ORDER BY {order_sql}
      LIMIT @lim
    """, {"city": city, "lim": limit})
    for r in rows:
        r["risk_band"] = _band(r.pop("risk_score"))
        r["observed"] = int(r["observed"])
    return {"city_id": city, "count": len(rows), "anomalies": rows}
