"""Pull rainfall from Open-Meteo (free, no key) into varuna.rainfall_hourly.

Two modes:
  --mode historical   archive-api hourly rain for a date range (backfill 2020-2025)
  --mode forecast     forecast-api next 7 days hourly rain (live use; is_forecast=TRUE)

One row per (city_id, grid_point_id, ts). Grid points come from the city config's
rainfall_grid (8 BBMP zone centroids for Bengaluru). Idempotent per mode+range:
loads to a staging table then MERGEs into rainfall_hourly.

    python ingestion/openmeteo_puller.py --city bengaluru --mode historical \
        --start 2020-01-01 --end 2025-06-30
    python ingestion/openmeteo_puller.py --city bengaluru --mode forecast
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

import requests
import yaml

REPO = Path(__file__).resolve().parents[1]
CONFIGS = REPO / "configs"
DATASET = "varuna"
LOCATION = "asia-south1"

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"


def fetch_point(url: str, lat: float, lng: float, params: dict) -> list[tuple]:
    """Return list of (ts_iso, rain_mm). Retries on transient errors."""
    q = {"latitude": lat, "longitude": lng, "hourly": "rain",
         "timezone": "UTC", **params}
    for attempt in range(4):
        try:
            r = requests.get(url, params=q, timeout=90)
            if r.status_code == 429:            # rate limited -> back off
                time.sleep(8 * (attempt + 1))
                continue
            r.raise_for_status()
            h = r.json().get("hourly", {})
            times = h.get("time", []) or []
            rain = h.get("rain", []) or []
            return [(t, (v if v is not None else 0.0)) for t, v in zip(times, rain)]
        except requests.RequestException as e:
            if attempt == 3:
                raise
            time.sleep(4 * (attempt + 1))
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True)
    ap.add_argument("--mode", choices=["historical", "forecast"], required=True)
    ap.add_argument("--start", help="YYYY-MM-DD (historical)")
    ap.add_argument("--end", help="YYYY-MM-DD (historical)")
    ap.add_argument("--dry-run", action="store_true", help="fetch but don't load BQ")
    args = ap.parse_args()

    cfg = yaml.safe_load((CONFIGS / f"{args.city}.yaml").read_text(encoding="utf-8"))
    city_id = cfg["city_id"]
    grid = cfg["rainfall_grid"]

    if args.mode == "historical":
        if not (args.start and args.end):
            sys.exit("--start and --end required for historical mode")
        url, params, is_forecast, source = (
            ARCHIVE, {"start_date": args.start, "end_date": args.end},
            False, "open-meteo-archive")
    else:
        url, params, is_forecast, source = (
            FORECAST, {"forecast_days": 7, "past_days": 1}, True, "open-meteo-forecast")

    rows = []
    for gp in grid:
        pts = fetch_point(url, gp["lat"], gp["lng"], params)
        for ts, mm in pts:
            rows.append({"city_id": city_id, "grid_point_id": gp["grid_point_id"],
                         "ts": ts + ":00" if len(ts) == 16 else ts,
                         "rain_mm": float(mm), "is_forecast": is_forecast,
                         "source": source})
        print(f"  {gp['grid_point_id']:16} {len(pts):>7,} hourly rows "
              f"({gp['lat']},{gp['lng']})")
    print(f"Fetched {len(rows):,} rows total ({args.mode}).")

    if args.dry_run:
        print("dry-run: skipping BQ load.")
        return 0

    _load_bq(city_id, rows, is_forecast)
    return 0


def _load_bq(city_id: str, rows: list[dict], is_forecast: bool):
    try:
        from google.cloud import bigquery
    except ImportError:
        sys.exit("google-cloud-bigquery not installed.")
    if not (os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")):
        sys.exit("Set GOOGLE_CLOUD_PROJECT + run `gcloud auth application-default login`.")

    client = bigquery.Client(location=LOCATION)
    ds = f"{client.project}.{DATASET}"
    stage = "rainfall_staging"
    schema = [
        bigquery.SchemaField("city_id", "STRING"),
        bigquery.SchemaField("grid_point_id", "STRING"),
        bigquery.SchemaField("ts", "TIMESTAMP"),
        bigquery.SchemaField("rain_mm", "FLOAT64"),
        bigquery.SchemaField("is_forecast", "BOOL"),
        bigquery.SchemaField("source", "STRING"),
    ]
    job_cfg = bigquery.LoadJobConfig(
        schema=schema, source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition="WRITE_TRUNCATE")
    data = "\n".join(json.dumps(r) for r in rows).encode("utf-8")
    client.load_table_from_file(io.BytesIO(data), f"{ds}.{stage}",
                                job_config=job_cfg).result()

    # MERGE: replace the same (city, point, ts, is_forecast) slice, insert the rest.
    client.query(f"""
        MERGE `{DATASET}.rainfall_hourly` T
        USING `{DATASET}.{stage}` S
        ON  T.city_id = S.city_id AND T.grid_point_id = S.grid_point_id
        AND T.ts = S.ts AND T.is_forecast = S.is_forecast
        WHEN MATCHED THEN UPDATE SET rain_mm = S.rain_mm, source = S.source
        WHEN NOT MATCHED THEN INSERT ROW
    """).result()
    client.query(f"DROP TABLE `{DATASET}.{stage}`").result()
    n = list(client.query(
        f"SELECT COUNT(*) c FROM `{DATASET}.rainfall_hourly` "
        f"WHERE city_id='{city_id}' AND is_forecast={str(is_forecast).upper()}"
    ).result())[0].c
    print(f"Loaded/merged into rainfall_hourly. Now {n:,} "
          f"{'forecast' if is_forecast else 'historical'} rows for {city_id}.")


if __name__ == "__main__":
    raise SystemExit(main())
