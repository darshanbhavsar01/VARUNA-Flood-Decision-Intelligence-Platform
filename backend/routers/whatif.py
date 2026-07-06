"""What-if rainfall simulator (§4 P1 #9). Re-scores every ward with the trained
BQML risk model after overriding the rainfall features for a hypothetical storm
(e.g. "80mm in 2 hours over Bommanahalli"). Returns base vs new score per ward.

Takes the latest scored day's feature row per ward as the baseline, overrides the
rain features for wards in the targeted zone (or citywide), and runs ML.PREDICT.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import bq
from ..services.settings import get_settings

router = APIRouter(prefix="/api/whatif", tags=["whatif"])

FEATURES = "risk_features"
MODEL = "risk_model"


class WhatIf(BaseModel):
    rain_mm: float                    # hypothetical rainfall total (mm)
    hours: int | None = None          # over how many hours (display only)
    zone: str | None = None           # target BBMP zone; None/'' = citywide
    city: str | None = None


def _band(s):
    return "high" if s >= 0.6 else "moderate" if s >= 0.3 else "low"


@router.post("")
def simulate(body: WhatIf):
    city = body.city or get_settings().default_city
    zone = body.zone or ""
    rain = float(body.rain_mm)

    rows = bq.query(f"""
      WITH latest AS (
        SELECT MAX(day) d FROM {bq.t(FEATURES)}
        WHERE city_id=@city AND split='test'
      ),
      base AS (
        SELECT f.*, w.zone AS _zone, w.ward_name AS _ward_name
        FROM {bq.t(FEATURES)} f
        JOIN {bq.t('wards')} w ON f.ward_id=w.ward_id AND w.city_id=@city
        WHERE f.city_id=@city AND f.split='test' AND f.day=(SELECT d FROM latest)
      ),
      scen AS (
        SELECT
          ward_id, _zone, _ward_name,
          -- override rain features for targeted wards; keep others at baseline
          IF(@zone='' OR _zone=@zone, @rain, rain_fcst_1d)          AS rain_fcst_1d,
          IF(@zone='' OR _zone=@zone, @rain, rain_prev_1d)          AS rain_prev_1d,
          IF(@zone='' OR _zone=@zone, rain_prev_3d+@rain, rain_prev_3d) AS rain_prev_3d,
          IF(@zone='' OR _zone=@zone, rain_prev_7d+@rain, rain_prev_7d) AS rain_prev_7d,
          is_low_lying, historical_flood_count, month,
          IF(@zone='' OR _zone=@zone, 1, is_monsoon)               AS is_monsoon,
          ward_flood_baseline, velocity_prev_1d, velocity_prev_3d
        FROM base
      ),
      pred AS (
        SELECT ward_id,
          (SELECT pp.prob FROM UNNEST(predicted_label_probs) pp WHERE pp.label=1) AS new_score
        FROM ML.PREDICT(MODEL {bq.t(MODEL)},
          (SELECT * EXCEPT(_zone, _ward_name) FROM scen))
      )
      SELECT s._ward_name AS ward_name, s._zone AS zone, p.ward_id,
             ROUND(p.new_score, 4) AS new_score,
             ROUND(IFNULL(r.score, 0), 4) AS base_score,
             (@zone='' OR s._zone=@zone) AS targeted
      FROM pred p
      JOIN scen s USING (ward_id)
      LEFT JOIN {bq.t('risk_scores')} r
        ON r.ward_id=p.ward_id AND r.city_id=@city AND r.horizon_hrs=24
      ORDER BY p.new_score DESC
    """, {"city": city, "zone": zone, "rain": rain})

    wards = [{
        "ward_id": r["ward_id"], "ward_name": r["ward_name"], "zone": r["zone"],
        "base_score": r["base_score"], "new_score": r["new_score"],
        "delta": round(r["new_score"] - r["base_score"], 4),
        "new_band": _band(r["new_score"]), "targeted": r["targeted"],
    } for r in rows]

    bands = {"high": 0, "moderate": 0, "low": 0}
    for w in wards:
        bands[w["new_band"]] += 1
    return {
        "city_id": city, "scenario": {"rain_mm": rain, "hours": body.hours,
                                      "zone": zone or "citywide"},
        "bands": bands, "wards": wards,
    }
