# Ingestion — VARUNA data foundation (§11 step 1)

Turns raw open-government data into VARUNA's canonical, multi-city-shaped tables.
City onboarding is **config-driven** (`configs/<city>.yaml`) — no city is hardcoded here.

## Run it
```bash
pip install -r requirements.txt
python ingestion/run_pipeline.py --city bengaluru            # local: download + normalize
python ingestion/run_pipeline.py --city bengaluru --load-bq  # + load BigQuery (needs GCP auth)
```

## Stages
| Script | Input | Output |
|---|---|---|
| `download_data.py` | `manifests/<city>.json` (resolved OpenCity URLs) | `data/raw/*` |
| `inspect_raw.py` | raw files | prints schemas (diagnostics only) |
| `normalize_geo.py` | ward + hazard KML | `data/processed/wards.geojson`, `wards.csv` |
| `normalize_grievances.py` | 6 grievance CSVs + `wards.csv` | `data/processed/grievances.csv` + reports |
| `load_bigquery.py` | processed files | BigQuery `varuna.*` tables |

## What's real vs. derived
- **Real, downloaded:** 766,648 BBMP grievances (2020–2025), 198-ward boundaries (2015 KML),
  270 flood-prone + 129 low-lying hazard points. All from data.opencity.in (see manifest).
- **Derived:** `category_norm` (shared taxonomy), per-ward `is_low_lying` /
  `historical_flood_count` (hazard points assigned to wards by point-in-polygon),
  `ward_id` on each grievance (fuzzy name join).

## Honest data caveats (kept current — §5)
- **Ward join ≈ 92.25%.** The remaining ~7.75% are **12 grievance wards absent from the
  2015/198-ward KML** (renamed or from a different delimitation vintage — e.g. *Jnanabharathi
  Ward* 18.3k rows, *Someshwara* 11.4k). They are listed explicitly in
  `configs/bengaluru.yaml → ward_join.known_absent` and forced to `unmatched` so fuzzy
  matching can't silently mis-assign them. Fixable by sourcing a matching-vintage ward map.
  Full audit: `data/processed/ward_join_report.md`.
- **Flood signal lives in Sub Category, not Category.** ~8,300 "water stagnation" complaints
  are filed under Category=*Road Maintenance(Engg)*; a category-only mapping would miss them.
  Normalization reads Category + Sub Category with drainage/waterlogging patterns prioritized
  over the greedy "road" match. Audit: `data/processed/category_map_report.md`.
- **Complaint reporting bias** (affluent/tech corridors report more) and **no drain-network
  data** remain — handled at the model/UI layer, not hidden.
- Grievance rows have **no lat/lng** in source → geolocation is ward-level only.
