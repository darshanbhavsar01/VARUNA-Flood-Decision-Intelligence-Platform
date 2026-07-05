"""Load VARUNA's processed data into BigQuery (dataset `varuna`, region asia-south1).

Run this once gcloud auth + a GCP project are available:
    export GOOGLE_CLOUD_PROJECT=your-project        # or set on Windows
    python ingestion/load_bigquery.py --city bengaluru

What it does:
  1. Creates the `varuna` dataset (asia-south1) if missing + all tables (bq_schema.sql).
  2. Loads `cities` from the city config.
  3. Loads `wards` — geometry parsed from wards.geojson into a real GEOGRAPHY column
     (staged as GeoJSON strings, then ST_GEOGFROMGEOJSON on insert).
  4. Loads `grievances` from grievances.csv with an explicit typed schema.

Costs nothing beyond free-tier storage/queries (<1GB). No always-on services.
This script is intentionally standalone and idempotent (WRITE_TRUNCATE per table).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
PROC = REPO / "data" / "processed"
CONFIGS = REPO / "configs"
DATASET = "varuna"
LOCATION = "asia-south1"


def _require_bq():
    try:
        from google.cloud import bigquery  # noqa: F401
    except ImportError:
        sys.exit("google-cloud-bigquery not installed. `pip install -r requirements.txt`")
    if not (os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")):
        sys.exit("Set GOOGLE_CLOUD_PROJECT and run `gcloud auth application-default login` "
                 "before loading BigQuery.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True)
    args = ap.parse_args()
    _require_bq()

    from google.cloud import bigquery

    cfg = yaml.safe_load((CONFIGS / f"{args.city}.yaml").read_text(encoding="utf-8"))
    client = bigquery.Client(location=LOCATION)
    ds_ref = f"{client.project}.{DATASET}"

    # 1. dataset + tables
    ds = bigquery.Dataset(ds_ref)
    ds.location = LOCATION
    client.create_dataset(ds, exists_ok=True)
    print(f"Dataset ready: {ds_ref} ({LOCATION})")
    ddl = (REPO / "ingestion" / "bq_schema.sql").read_text(encoding="utf-8")
    # run each statement (skip the CREATE SCHEMA — handled above via API)
    for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
        if stmt.upper().startswith("CREATE SCHEMA"):
            continue
        client.query(stmt.replace("`varuna.", f"`{DATASET}.")).result()
    print("Tables ensured from bq_schema.sql")

    # 2. cities
    city_row = {
        "city_id": cfg["city_id"], "name": cfg["name"],
        "bbox": [float(x) for x in cfg["bbox"]], "mode": cfg["mode"],
        "config_json": json.dumps({k: cfg[k] for k in
                                   ("rainfall_grid", "flood_signal_categories")}),
    }
    _load_json(client, ds_ref, "cities", [city_row], write="WRITE_TRUNCATE")
    print("Loaded cities")

    # 3. wards with GEOGRAPHY (stage geojson-string -> ST_GEOGFROMGEOJSON)
    gj = json.loads((PROC / "wards.geojson").read_text(encoding="utf-8"))
    ward_rows = []
    for feat in gj["features"]:
        p = feat["properties"]
        ward_rows.append({
            "city_id": p["city_id"], "ward_id": int(p["ward_id"]),
            "ward_name": p["ward_name"], "zone": p["zone"],
            "is_low_lying": bool(p["is_low_lying"]),
            "historical_flood_count": int(p["historical_flood_count"]),
            "geom_geojson": json.dumps(feat["geometry"]),
        })
    stage = f"{DATASET}.wards_staging"
    _load_json(client, ds_ref, "wards_staging", ward_rows, write="WRITE_TRUNCATE",
               autodetect=True)
    client.query(f"""
        CREATE OR REPLACE TABLE `{DATASET}.wards` AS
        SELECT city_id, ward_id, ward_name, zone,
               SAFE.ST_GEOGFROMGEOJSON(geom_geojson, make_valid => TRUE) AS geometry,
               is_low_lying, historical_flood_count
        FROM `{stage}`
    """).result()
    client.query(f"DROP TABLE `{stage}`").result()
    print(f"Loaded wards ({len(ward_rows)}) with GEOGRAPHY")

    # 4. grievances (typed schema, from CSV)
    schema = [
        bigquery.SchemaField("city_id", "STRING"),
        bigquery.SchemaField("grievance_id", "STRING"),
        bigquery.SchemaField("ward_id", "INT64"),
        bigquery.SchemaField("ward_name_raw", "STRING"),
        bigquery.SchemaField("ward_name_canon", "STRING"),
        bigquery.SchemaField("category_raw", "STRING"),
        bigquery.SchemaField("sub_category_raw", "STRING"),
        bigquery.SchemaField("category_norm", "STRING"),
        bigquery.SchemaField("description", "STRING"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
        bigquery.SchemaField("status", "STRING"),
        bigquery.SchemaField("lat", "FLOAT64"),
        bigquery.SchemaField("lng", "FLOAT64"),
    ]
    job_cfg = bigquery.LoadJobConfig(
        schema=schema, skip_leading_rows=1,
        source_format=bigquery.SourceFormat.CSV,
        write_disposition="WRITE_TRUNCATE", allow_quoted_newlines=True,
    )
    with open(PROC / "grievances.csv", "rb") as f:
        job = client.load_table_from_file(f, f"{ds_ref}.grievances", job_config=job_cfg)
    job.result()
    n = client.get_table(f"{ds_ref}.grievances").num_rows
    print(f"Loaded grievances ({n:,} rows)")

    print("\nDone. rainfall_hourly / risk_scores / anomalies are populated by later steps.")
    return 0


def _load_json(client, ds_ref, table, rows, write="WRITE_APPEND", autodetect=False):
    from google.cloud import bigquery
    cfg = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=write, autodetect=autodetect,
    )
    data = "\n".join(json.dumps(r) for r in rows).encode("utf-8")
    import io
    job = client.load_table_from_file(io.BytesIO(data), f"{ds_ref}.{table}", job_config=cfg)
    job.result()


if __name__ == "__main__":
    raise SystemExit(main())
