-- VARUNA BigQuery schema (§7). Multi-city from day one: every table carries city_id.
-- Geography is generic: city -> zone -> ward. Nothing hardcodes "BBMP".
-- Dataset lives in region asia-south1 (§10). Run: bq query --use_legacy_sql=false < bq_schema.sql
-- (or via ingestion/load_bigquery.py, which creates the dataset + loads data).

CREATE SCHEMA IF NOT EXISTS `varuna`
  OPTIONS (location = 'asia-south1');

CREATE TABLE IF NOT EXISTS `varuna.cities` (
  city_id      STRING NOT NULL,
  name         STRING,
  bbox         ARRAY<FLOAT64>,        -- [min_lng, min_lat, max_lng, max_lat]
  mode         STRING,                -- 'full' | 'rain_only'
  config_json  JSON
);

CREATE TABLE IF NOT EXISTS `varuna.wards` (
  city_id                 STRING NOT NULL,
  ward_id                 INT64  NOT NULL,
  ward_name               STRING,
  zone                    STRING,
  geometry                GEOGRAPHY,
  is_low_lying            BOOL,
  historical_flood_count  INT64
);

CREATE TABLE IF NOT EXISTS `varuna.grievances` (
  city_id          STRING NOT NULL,
  grievance_id     STRING NOT NULL,
  ward_id          INT64,             -- nullable: ~8% of BLR rows are known-absent wards
  ward_name_raw    STRING,
  ward_name_canon  STRING,
  category_raw     STRING,
  sub_category_raw STRING,
  category_norm    STRING,            -- shared taxonomy (§7)
  description      STRING,
  created_at       TIMESTAMP,
  status           STRING,
  lat              FLOAT64,
  lng              FLOAT64
)
PARTITION BY DATE(created_at)
CLUSTER BY city_id, ward_id, category_norm;

CREATE TABLE IF NOT EXISTS `varuna.rainfall_hourly` (
  city_id       STRING NOT NULL,
  grid_point_id STRING NOT NULL,
  ts            TIMESTAMP NOT NULL,
  rain_mm       FLOAT64,
  is_forecast   BOOL,
  source        STRING
)
PARTITION BY DATE(ts)
CLUSTER BY city_id, grid_point_id;

CREATE TABLE IF NOT EXISTS `varuna.risk_scores` (
  city_id      STRING NOT NULL,
  ward_id      INT64  NOT NULL,
  horizon_hrs  INT64,                 -- 6 | 24 | 48
  score        FLOAT64,
  computed_at  TIMESTAMP,
  top_features JSON                   -- per-ward feature attributions (ML.EXPLAIN_PREDICT)
)
CLUSTER BY city_id, ward_id;

CREATE TABLE IF NOT EXISTS `varuna.anomalies` (
  city_id       STRING NOT NULL,
  ward_id       INT64,
  category_norm STRING,
  ts            TIMESTAMP,
  observed      FLOAT64,
  expected      FLOAT64,
  deviation     FLOAT64,
  status        STRING
)
CLUSTER BY city_id, ward_id;
