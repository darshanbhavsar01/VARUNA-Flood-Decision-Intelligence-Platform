"""Thin BigQuery access layer. One cached client; parameterized queries only.

Keeps a `t()` helper so table names always resolve to the configured dataset,
keeping everything multi-city / multi-env clean.
"""
from __future__ import annotations

import functools

from google.cloud import bigquery

from .settings import get_settings


@functools.lru_cache
def client() -> bigquery.Client:
    s = get_settings()
    kwargs = {"location": s.bq_location}
    if s.google_cloud_project:
        kwargs["project"] = s.google_cloud_project
    return bigquery.Client(**kwargs)


def t(name: str) -> str:
    """Fully-qualified `project.dataset.table` backticked for SQL."""
    c = client()
    return f"`{c.project}.{get_settings().bq_dataset}.{name}`"


def _param(name: str, value):
    if isinstance(value, bool):
        typ = "BOOL"
    elif isinstance(value, int):
        typ = "INT64"
    elif isinstance(value, float):
        typ = "FLOAT64"
    else:
        typ = "STRING"
    return bigquery.ScalarQueryParameter(name, typ, value)


def query(sql: str, params: dict | None = None,
          maximum_bytes_billed: int | None = None) -> list[dict]:
    job_config = bigquery.QueryJobConfig(
        query_parameters=[_param(k, v) for k, v in (params or {}).items()])
    if maximum_bytes_billed:
        job_config.maximum_bytes_billed = maximum_bytes_billed
    rows = client().query(sql, job_config=job_config).result()
    return [dict(r) for r in rows]


def dry_run_bytes(sql: str, params: dict | None = None) -> int:
    """Estimate bytes a query would scan (for NL-to-SQL guardrails, §9)."""
    job_config = bigquery.QueryJobConfig(
        dry_run=True, use_query_cache=False,
        query_parameters=[_param(k, v) for k, v in (params or {}).items()])
    job = client().query(sql, job_config=job_config)
    return int(job.total_bytes_processed or 0)
