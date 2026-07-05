"""Download raw datasets for a city from its manifest into data/raw/.

Usage:
    python ingestion/download_data.py --city bengaluru
    python ingestion/download_data.py --city bengaluru --force

Idempotent: skips files that already exist (non-empty) unless --force.
Streams downloads so large grievance CSVs don't blow up memory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw"
MANIFESTS = REPO / "ingestion" / "manifests"

HEADERS = {"User-Agent": "VARUNA-ingestion/0.1 (hackathon prototype)"}


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def download(url: str, dest: Path, force: bool) -> int:
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"  skip (exists {human(dest.stat().st_size)}): {dest.name}")
        return dest.stat().st_size
    tmp = dest.with_suffix(dest.suffix + ".part")
    total = 0
    with requests.get(url, headers=HEADERS, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
    tmp.replace(dest)
    print(f"  OK {human(total)}: {dest.name}")
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True, help="manifest name, e.g. bengaluru")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    manifest_path = MANIFESTS / f"{args.city}.json"
    if not manifest_path.exists():
        sys.exit(f"No manifest at {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    RAW.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {len(manifest['resources'])} resources for city_id="
          f"{manifest['city_id']} -> {RAW}")

    grand = 0
    failures = []
    for res in manifest["resources"]:
        dest = RAW / res["name"]
        try:
            grand += download(res["url"], dest, args.force)
        except Exception as e:  # noqa: BLE001 — report and continue
            print(f"  FAIL {res['name']}: {e}")
            failures.append(res["name"])

    print(f"\nTotal downloaded/present: {human(grand)}")
    if failures:
        print(f"FAILURES ({len(failures)}): {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
