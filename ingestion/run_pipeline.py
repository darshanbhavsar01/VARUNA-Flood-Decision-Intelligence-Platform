"""One-command data foundation (§11 step 1) for a city.

    python ingestion/run_pipeline.py --city bengaluru [--load-bq]

Runs: download -> normalize_geo -> normalize_grievances, then (optionally, if
GCP creds are present) load_bigquery. Each stage is idempotent.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def step(name, *cmd):
    print(f"\n{'='*70}\n>>> {name}\n{'='*70}")
    r = subprocess.run([sys.executable, *cmd], cwd=REPO)
    if r.returncode != 0:
        sys.exit(f"Stage failed: {name} (exit {r.returncode})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True)
    ap.add_argument("--load-bq", action="store_true",
                    help="also load into BigQuery (needs GOOGLE_CLOUD_PROJECT + auth)")
    args = ap.parse_args()

    step("Download raw datasets", "ingestion/download_data.py", "--city", args.city)
    step("Normalize geography", "ingestion/normalize_geo.py", "--city", args.city)
    step("Normalize grievances", "ingestion/normalize_grievances.py", "--city", args.city)
    if args.load_bq:
        step("Load BigQuery", "ingestion/load_bigquery.py", "--city", args.city)
    print("\nData foundation complete. See data/processed/*_report.md for the audit.")


if __name__ == "__main__":
    main()
