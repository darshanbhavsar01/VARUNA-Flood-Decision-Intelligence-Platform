"""Build the per-(ward, day) training table for the flood-risk model (§8a).

Creates two BigQuery tables in `varuna`:
  - ward_grid_map(city_id, ward_id, grid_point_id)  -- nearest rainfall grid point
  - risk_features(...)                               -- label + features, one row per ward-day

Design (predict a ward's waterlogging risk for a target day D):
  label(ward, D) = 1 if flood-signal complaints on D >= LABEL_THRESHOLD (proxy for
                   waterlogging; documented reporting-bias caveat).
  Features known as of the start of D (rain_fcst_1d = D's rain, supplied by the
  live forecast at inference; everything else is strictly pre-D so no leakage):
    rain_fcst_1d, rain_prev_1d, rain_prev_3d, rain_prev_7d  (mm, nearest grid point)
    is_low_lying, historical_flood_count                    (static ward hazard)
    month, is_monsoon                                       (seasonality)
    ward_flood_baseline    (ward mean daily flood complaints over the TRAIN window
                            -> reporting-propensity control)
    velocity_prev_1d, velocity_prev_3d  (flood complaints in ward just before D --
                            the citizen "human sensor" early-warning signal)
  split = 'train' (<=2023) | 'val' (2024) | 'test' (2025)   (temporal, §8a)

Usage:  python ml/build_features.py --city bengaluru
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
CONFIGS = REPO / "configs"
DATASET = "varuna"
LOCATION = "asia-south1"
LABEL_THRESHOLD = 2       # >=2 flood complaints/day = positive (cuts single-report noise)
TRAIN_END = "2023-12-31"  # baseline computed over data <= this to limit leakage


def grid_struct_sql(grid: list[dict]) -> str:
    parts = [f"STRUCT('{g['grid_point_id']}' AS gid, "
             f"ST_GEOGPOINT({g['lng']}, {g['lat']}) AS g)" for g in grid]
    return "SELECT * FROM UNNEST([\n      " + ",\n      ".join(parts) + "\n    ])"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True)
    args = ap.parse_args()
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        sys.exit("Set GOOGLE_CLOUD_PROJECT + `gcloud auth application-default login`.")
    from google.cloud import bigquery

    cfg = yaml.safe_load((CONFIGS / f"{args.city}.yaml").read_text(encoding="utf-8"))
    city = cfg["city_id"]
    flood = ", ".join(f"'{c}'" for c in cfg["flood_signal_categories"])
    client = bigquery.Client(location=LOCATION)

    # 1) nearest rainfall grid point per ward (config-driven; geometry-based)
    client.query(f"""
    CREATE OR REPLACE TABLE `{DATASET}.ward_grid_map` AS
    WITH grid AS ({grid_struct_sql(cfg['rainfall_grid'])}),
    wc AS (SELECT ward_id, ST_CENTROID(geometry) c
           FROM `{DATASET}.wards` WHERE city_id='{city}')
    SELECT '{city}' AS city_id, wc.ward_id,
      ARRAY_AGG(grid.gid ORDER BY ST_DISTANCE(wc.c, grid.g) LIMIT 1)[OFFSET(0)]
        AS grid_point_id
    FROM wc CROSS JOIN grid GROUP BY wc.ward_id
    """).result()
    print("Built ward_grid_map (nearest grid point per ward)")

    # 2) feature table
    sql = f"""
    CREATE OR REPLACE TABLE `{DATASET}.risk_features`
    CLUSTER BY split, ward_id AS
    WITH
    -- daily rainfall per grid point (historical actuals)
    rain_g AS (
      SELECT grid_point_id, DATE(ts) d, SUM(rain_mm) mm
      FROM `{DATASET}.rainfall_hourly`
      WHERE city_id='{city}' AND is_forecast=FALSE
      GROUP BY grid_point_id, d
    ),
    -- daily rainfall per ward (via nearest grid point)
    rain_w AS (
      SELECT m.ward_id, r.d, r.mm
      FROM rain_g r JOIN `{DATASET}.ward_grid_map` m USING (grid_point_id)
    ),
    -- daily flood-signal complaint counts per ward
    flood_w AS (
      SELECT ward_id, DATE(created_at) d, COUNT(*) n_flood
      FROM `{DATASET}.grievances`
      WHERE city_id='{city}' AND ward_id IS NOT NULL
        AND category_norm IN ({flood})
      GROUP BY ward_id, d
    ),
    -- per-ward reporting-propensity baseline (TRAIN window only -> limits leakage)
    baseline AS (
      SELECT ward_id, AVG(n_flood) AS ward_flood_baseline FROM (
        SELECT w.ward_id, cal.d, IFNULL(f.n_flood, 0) n_flood
        FROM (SELECT DISTINCT ward_id FROM `{DATASET}.ward_grid_map`) w
        CROSS JOIN (SELECT DISTINCT d FROM rain_w WHERE d <= '{TRAIN_END}') cal
        LEFT JOIN flood_w f ON f.ward_id=w.ward_id AND f.d=cal.d
      ) GROUP BY ward_id
    ),
    -- every ward x every day in the rainfall calendar
    spine AS (
      SELECT w.ward_id, cal.d
      FROM (SELECT DISTINCT ward_id FROM `{DATASET}.ward_grid_map`) w
      CROSS JOIN (SELECT DISTINCT d FROM rain_w) cal
    )
    SELECT
      '{city}' AS city_id, s.ward_id, s.d AS day,
      -- label
      IF(IFNULL(ft.n_flood,0) >= {LABEL_THRESHOLD}, 1, 0) AS label,
      -- rainfall features (mm)
      IFNULL(r0.mm,0)                                   AS rain_fcst_1d,
      IFNULL(r1.mm,0)                                   AS rain_prev_1d,
      IFNULL((SELECT SUM(mm) FROM rain_w x WHERE x.ward_id=s.ward_id
              AND x.d BETWEEN DATE_SUB(s.d,INTERVAL 3 DAY) AND DATE_SUB(s.d,INTERVAL 1 DAY)),0)
                                                        AS rain_prev_3d,
      IFNULL((SELECT SUM(mm) FROM rain_w x WHERE x.ward_id=s.ward_id
              AND x.d BETWEEN DATE_SUB(s.d,INTERVAL 7 DAY) AND DATE_SUB(s.d,INTERVAL 1 DAY)),0)
                                                        AS rain_prev_7d,
      -- static ward hazard
      wd.is_low_lying, wd.historical_flood_count,
      -- seasonality
      EXTRACT(MONTH FROM s.d) AS month,
      IF(EXTRACT(MONTH FROM s.d) BETWEEN 6 AND 10, 1, 0) AS is_monsoon,
      -- reporting-propensity baseline
      IFNULL(b.ward_flood_baseline,0)                   AS ward_flood_baseline,
      -- citizen "human sensor" early-warning velocity
      IFNULL(fp1.n_flood,0)                             AS velocity_prev_1d,
      IFNULL((SELECT SUM(n_flood) FROM flood_w x WHERE x.ward_id=s.ward_id
              AND x.d BETWEEN DATE_SUB(s.d,INTERVAL 3 DAY) AND DATE_SUB(s.d,INTERVAL 1 DAY)),0)
                                                        AS velocity_prev_3d,
      -- temporal split
      CASE WHEN s.d <= '{TRAIN_END}' THEN 'train'
           WHEN s.d <  '2025-01-01' THEN 'val' ELSE 'test' END AS split
    FROM spine s
    JOIN `{DATASET}.wards` wd ON wd.city_id='{city}' AND wd.ward_id=s.ward_id
    LEFT JOIN baseline b       ON b.ward_id=s.ward_id
    LEFT JOIN flood_w  ft ON ft.ward_id=s.ward_id AND ft.d=s.d
    LEFT JOIN flood_w  fp1 ON fp1.ward_id=s.ward_id AND fp1.d=DATE_SUB(s.d,INTERVAL 1 DAY)
    LEFT JOIN rain_w   r0 ON r0.ward_id=s.ward_id AND r0.d=s.d
    LEFT JOIN rain_w   r1 ON r1.ward_id=s.ward_id AND r1.d=DATE_SUB(s.d,INTERVAL 1 DAY)
    """
    client.query(sql).result()
    print("Built risk_features")

    # 3) summary
    for row in client.query(f"""
      SELECT split, COUNT(*) n, SUM(label) pos,
             ROUND(100*SUM(label)/COUNT(*),3) pos_pct,
             MIN(day) min_d, MAX(day) max_d
      FROM `{DATASET}.risk_features` GROUP BY split ORDER BY min_d
    """).result():
        print(f"  {row.split:5} rows={row.n:>7,} pos={row.pos:>5,} "
              f"({row.pos_pct}%)  {row.min_d}..{row.max_d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
