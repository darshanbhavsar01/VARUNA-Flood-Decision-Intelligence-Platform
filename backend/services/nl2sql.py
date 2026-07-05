"""NL-to-SQL for CityPulse (§9): Gemini Flash + hard guardrails.

Guardrails (defense in depth — the LLM is never trusted):
  - generation: schema + category vocabulary + few-shots steer valid SQL.
  - validation: must be a single SELECT/WITH statement; DML/DDL keywords banned;
    only allowlisted tables; LIMIT enforced; then a dry-run bytes-scanned cap.
  - on execution error: retry ONCE, feeding the error back to the model.
"""
from __future__ import annotations

import re

from . import bq, gemini
from .settings import get_settings

# Tables the analyst may read (§7). Everything else is rejected.
ALLOWED_TABLES = {
    "grievances", "wards", "rainfall_hourly", "risk_scores", "anomalies", "cities",
}
MAX_LIMIT = 1000
MAX_BYTES = 300 * 1024 * 1024          # 300 MB dry-run cap
BANNED = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|MERGE|TRUNCATE|GRANT|REVOKE|"
    r"CALL|EXPORT|LOAD|REPLACE)\b", re.I)

SCHEMA_DOC = """
You write BigQuery Standard SQL over the `varuna` dataset. Tables (refer to them
as varuna.<table>):

varuna.grievances  -- 766k BBMP citizen complaints, 2020-2025 (one row per complaint)
  city_id STRING, grievance_id STRING, ward_id INT64 (nullable),
  ward_name_canon STRING, category_raw STRING, sub_category_raw STRING,
  category_norm STRING, created_at TIMESTAMP, status STRING
  -- category_norm ∈ WATERLOGGING, DRAINAGE, GARBAGE, ROADS, WATER_SUPPLY,
  --   STREETLIGHT, OTHER   (use these, NOT category_raw, for topic filters)
  -- flood signal = category_norm IN ('WATERLOGGING','DRAINAGE')

varuna.wards  -- 198 Bengaluru wards
  city_id STRING, ward_id INT64, ward_name STRING, zone STRING,
  is_low_lying BOOL, historical_flood_count INT64, geometry GEOGRAPHY
  -- 8 zones: East, West, South, Bommanahalli, Mahadevapura,
  --   Rajarajeswari Nagar, Yelahanka, Dasarahalli
  -- join grievances to wards on ward_id (both filtered by city_id)

varuna.rainfall_hourly  -- hourly rain per zone grid point
  city_id STRING, grid_point_id STRING, ts TIMESTAMP, rain_mm FLOAT64, is_forecast BOOL

varuna.risk_scores  -- latest model risk per ward
  city_id STRING, ward_id INT64, horizon_hrs INT64, score FLOAT64, computed_at TIMESTAMP

Rules:
  - Output ONE SELECT (or WITH ... SELECT) statement only. No DML/DDL, no semicolons.
  - Always filter city_id = 'blr'.
  - Prefer joining ward_id -> varuna.wards for human-readable ward_name.
  - Use category_norm for complaint topics. Dates via EXTRACT / DATE / TIMESTAMP.
  - Always include a sensible LIMIT (<= 1000).
  - Return ONLY the SQL, no markdown, no explanation.
""".strip()

FEWSHOT = """
Q: How many waterlogging complaints were filed in 2024?
SQL: SELECT COUNT(*) AS complaints FROM varuna.grievances
WHERE city_id='blr' AND category_norm='WATERLOGGING'
AND EXTRACT(YEAR FROM created_at)=2024 LIMIT 1000

Q: Top 5 wards by drainage complaints all-time
SQL: SELECT w.ward_name, COUNT(*) AS drainage_complaints
FROM varuna.grievances g JOIN varuna.wards w
ON g.ward_id=w.ward_id AND w.city_id='blr'
WHERE g.city_id='blr' AND g.category_norm='DRAINAGE'
GROUP BY w.ward_name ORDER BY drainage_complaints DESC LIMIT 5

Q: Monthly waterlogging complaint trend in 2023
SQL: SELECT FORMAT_DATE('%Y-%m', DATE(created_at)) AS month, COUNT(*) AS complaints
FROM varuna.grievances WHERE city_id='blr' AND category_norm='WATERLOGGING'
AND EXTRACT(YEAR FROM created_at)=2023 GROUP BY month ORDER BY month LIMIT 1000

Q: Compare drainage complaints between Mahadevapura and Bommanahalli zones
SQL: SELECT w.zone, COUNT(*) AS drainage_complaints
FROM varuna.grievances g JOIN varuna.wards w
ON g.ward_id=w.ward_id AND w.city_id='blr'
WHERE g.city_id='blr' AND g.category_norm='DRAINAGE'
AND w.zone IN ('Mahadevapura','Bommanahalli')
GROUP BY w.zone ORDER BY drainage_complaints DESC LIMIT 1000

Q: Which 10 wards have the highest current flood risk?
SQL: SELECT w.ward_name, r.score AS risk_score
FROM varuna.risk_scores r JOIN varuna.wards w
ON r.ward_id=w.ward_id AND w.city_id='blr'
WHERE r.city_id='blr' AND r.horizon_hrs=24
ORDER BY r.score DESC LIMIT 10
""".strip()


def _strip_fences(sql: str) -> str:
    sql = sql.strip()
    if sql.startswith("```"):
        sql = re.sub(r"^```[a-zA-Z]*\n?", "", sql)
        sql = re.sub(r"\n?```$", "", sql)
    return sql.strip().rstrip(";").strip()


def _referenced_tables(sql: str) -> set[str]:
    # match varuna.<table> and bare project-qualified forms
    return {m.lower() for m in re.findall(r"varuna\.([A-Za-z_][A-Za-z0-9_]*)", sql)}


def validate(sql: str) -> str:
    """Raise ValueError if unsafe; return the sanitized (LIMIT-enforced) SQL."""
    sql = _strip_fences(sql)
    if not sql:
        raise ValueError("empty SQL")
    low = sql.lstrip("(").lstrip().lower()
    if not (low.startswith("select") or low.startswith("with")):
        raise ValueError("only SELECT/WITH queries are allowed")
    if ";" in sql:
        raise ValueError("multiple statements are not allowed")
    if BANNED.search(sql):
        raise ValueError("data-modifying keywords are not allowed")
    tables = _referenced_tables(sql)
    if not tables:
        raise ValueError("query must reference a varuna.<table>")
    bad = tables - ALLOWED_TABLES
    if bad:
        raise ValueError(f"table(s) not allowed: {', '.join(sorted(bad))}")
    if not re.search(r"\blimit\b", sql, re.I):
        sql = f"{sql}\nLIMIT {MAX_LIMIT}"
    return sql


def _to_fq(sql: str) -> str:
    """Rewrite varuna.<table> -> `project.dataset.table` for execution."""
    c = bq.client()
    ds = get_settings().bq_dataset
    return re.sub(r"\bvaruna\.([A-Za-z_][A-Za-z0-9_]*)",
                  lambda m: f"`{c.project}.{ds}.{m.group(1)}`", sql)


def generate_sql(question: str, error_hint: str | None = None) -> str:
    prompt = f"{SCHEMA_DOC}\n\nExamples:\n{FEWSHOT}\n\nQ: {question}\nSQL:"
    if error_hint:
        prompt += (f"\n\n(Your previous SQL failed with: {error_hint}\n"
                   f"Fix it and return only corrected SQL.)")
    return _strip_fences(gemini.generate(prompt, temperature=0.1))


def run(question: str) -> dict:
    """Full NL-to-SQL cycle with one retry. Returns result dict for the router."""
    attempts = []
    sql = None
    for attempt in range(2):
        try:
            raw = generate_sql(question, error_hint=attempts[-1] if attempts else None)
            sql = validate(raw)
            fq = _to_fq(sql)
            scanned = bq.dry_run_bytes(fq)
            if scanned > MAX_BYTES:
                raise ValueError(
                    f"query would scan {scanned/1e6:.0f} MB (> "
                    f"{MAX_BYTES/1e6:.0f} MB cap); please narrow it")
            rows = bq.query(fq, maximum_bytes_billed=MAX_BYTES)
            cols = list(rows[0].keys()) if rows else []
            return {"ok": True, "sql": sql, "columns": cols,
                    "rows": rows, "bytes_scanned": scanned, "attempts": attempt + 1}
        except gemini.GeminiRateLimited:
            raise                                  # let the router show a clear message
        except Exception as e:  # noqa: BLE001
            attempts.append(str(e)[:300])
    return {"ok": False, "sql": sql, "error": attempts[-1] if attempts else "unknown",
            "columns": [], "rows": [], "attempts": len(attempts)}
