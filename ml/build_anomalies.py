"""Anomaly detection for the 'citizens as sensors' feed (§8b).

Flags days where a ward's flood-signal (WATERLOGGING/DRAINAGE) complaint count
spikes far above its own recent baseline — an early-warning signal that can fire
before a rainfall model alone would. Uses a rolling per-(ward, category) baseline +
z-score/ratio over a zero-filled daily spine (simple > sophisticated, per §8b),
and writes to the `anomalies` BigQuery table.

    python ml/build_anomalies.py --city bengaluru

Output rows: city_id, ward_id, category_norm, ts, observed, expected, deviation, status
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

WINDOW_DAYS = 28        # trailing baseline window
MIN_OBSERVED = 3        # ignore tiny counts (noise)
Z_THRESHOLD = 2.5       # obs must exceed mean + Z*std ...
RATIO_THRESHOLD = 3.0   # ... AND be >= this multiple of the smoothed baseline
OUTPUT_FROM = "2024-01-01"   # surface anomalies from here on (history feeds baseline)


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

    client.query(f"DELETE FROM `{DATASET}.anomalies` "
                 f"WHERE city_id='{city}'").result()
    client.query(f"""
    INSERT INTO `{DATASET}.anomalies`
      (city_id, ward_id, category_norm, ts, observed, expected, deviation, status)
    WITH cats AS (SELECT cat FROM UNNEST([{flood}]) cat),
    cal AS (
      SELECT d FROM UNNEST(GENERATE_DATE_ARRAY(
        (SELECT MIN(DATE(created_at)) FROM `{DATASET}.grievances` WHERE city_id='{city}'),
        (SELECT MAX(DATE(created_at)) FROM `{DATASET}.grievances` WHERE city_id='{city}')
      )) d
    ),
    counts AS (
      SELECT ward_id, category_norm AS cat, DATE(created_at) d, COUNT(*) obs
      FROM `{DATASET}.grievances`
      WHERE city_id='{city}' AND ward_id IS NOT NULL AND category_norm IN ({flood})
      GROUP BY ward_id, cat, d
    ),
    spine AS (
      SELECT w.ward_id, c.cat, cal.d, IFNULL(k.obs, 0) AS obs
      FROM (SELECT DISTINCT ward_id FROM `{DATASET}.wards` WHERE city_id='{city}') w
      CROSS JOIN cats c CROSS JOIN cal
      LEFT JOIN counts k ON k.ward_id=w.ward_id AND k.cat=c.cat AND k.d=cal.d
    ),
    rolled AS (
      SELECT ward_id, cat, d, obs,
        AVG(obs)    OVER win AS mean,
        STDDEV(obs) OVER win AS std
      FROM spine
      WINDOW win AS (PARTITION BY ward_id, cat ORDER BY UNIX_DATE(d)
                     RANGE BETWEEN {WINDOW_DAYS} PRECEDING AND 1 PRECEDING)
    )
    SELECT '{city}' AS city_id, ward_id, cat AS category_norm,
           TIMESTAMP(d) AS ts,
           CAST(obs AS FLOAT64) AS observed,
           ROUND(IFNULL(mean, 0), 3) AS expected,
           ROUND(obs / (IFNULL(mean, 0) + 0.5), 2) AS deviation,
           'open' AS status
    FROM rolled
    WHERE d >= '{OUTPUT_FROM}'
      AND obs >= {MIN_OBSERVED}
      AND obs >= IFNULL(mean, 0) + {Z_THRESHOLD} * IFNULL(std, 0)
      AND obs / (IFNULL(mean, 0) + 0.5) >= {RATIO_THRESHOLD}
    ORDER BY ts DESC, deviation DESC
    """).result()

    n = list(client.query(
        f"SELECT COUNT(*) c FROM `{DATASET}.anomalies`").result())[0].c
    print(f"Wrote {n} anomalies to `{DATASET}.anomalies`")
    print("\nTop by deviation:")
    for r in client.query(f"""
      SELECT a.ts, w.ward_name, w.zone, a.category_norm,
             a.observed, a.expected, a.deviation
      FROM `{DATASET}.anomalies` a JOIN `{DATASET}.wards` w USING (ward_id)
      WHERE w.city_id='{city}'
      ORDER BY a.deviation DESC LIMIT 12
    """).result():
        print(f"  {r.ts.date()} {r.ward_name:16} {r.category_norm:12} "
              f"obs={r.observed:.0f} exp={r.expected:.2f} dev={r.deviation:.1f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
