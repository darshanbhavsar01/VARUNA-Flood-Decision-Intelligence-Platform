"""Firestore access for real-time citizen reports (§6, §7 — reports live in Firestore).

Collection `citizen_reports`. Free-tier native mode. Degrades gracefully: if
Firestore isn't reachable, callers surface a readable error instead of crashing.
"""
from __future__ import annotations

import functools

from .settings import get_settings

COLLECTION = "citizen_reports"


class FirestoreError(RuntimeError):
    pass


@functools.lru_cache
def client():
    try:
        from google.cloud import firestore
    except ImportError as e:
        raise FirestoreError("google-cloud-firestore not installed") from e
    s = get_settings()
    kwargs = {}
    if s.google_cloud_project:
        kwargs["project"] = s.google_cloud_project
    return firestore.Client(**kwargs)


def add_report(doc: dict) -> dict:
    from google.cloud import firestore
    doc = {**doc, "created_at": firestore.SERVER_TIMESTAMP}
    ref = client().collection(COLLECTION).document()
    ref.set(doc)
    snap = ref.get()
    return _serialize(ref.id, snap.to_dict())


def list_reports(city_id: str, limit: int = 100) -> list[dict]:
    # single-field filter (auto-indexed) then sort client-side -> avoids needing
    # a composite index; fine at prototype scale (hundreds of reports).
    from google.cloud.firestore_v1.base_query import FieldFilter
    q = (client().collection(COLLECTION)
         .where(filter=FieldFilter("city_id", "==", city_id))
         .limit(500))
    docs = [_serialize(d.id, d.to_dict()) for d in q.stream()]
    docs.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return docs[:limit]


def _serialize(doc_id: str, data: dict | None) -> dict:
    data = dict(data or {})
    ts = data.get("created_at")
    if ts is not None and hasattr(ts, "isoformat"):
        data["created_at"] = ts.isoformat()
    data["id"] = doc_id
    return data
