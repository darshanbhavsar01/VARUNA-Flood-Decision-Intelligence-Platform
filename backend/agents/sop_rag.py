"""RAG over disaster-management SOP PDFs for the ResponsePlanner agent (§9).

Loads the bundled sop_index.json (built by ingestion/build_sop_index.py), embeds the
query with Gemini, and returns the top-k most similar SOP passages with their source
citation + page — so every agent recommendation can cite the SOP that justifies it.

Pure-Python cosine over a few hundred chunks — no vector DB, no extra infra (§6).
"""
from __future__ import annotations

import functools
import json
import math
from pathlib import Path

from ..services import gemini

INDEX_PATH = Path(__file__).resolve().parent / "sop_index.json"


@functools.lru_cache
def _index() -> dict:
    if not INDEX_PATH.exists():
        return {"chunks": [], "sources": [], "dim": 0}
    data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    for c in data["chunks"]:
        v = c["embedding"]
        c["_norm"] = math.sqrt(sum(x * x for x in v)) or 1.0
    return data


def available() -> bool:
    return bool(_index()["chunks"])


def sources() -> list[str]:
    return _index().get("sources", [])


def _cosine(q: list[float], qnorm: float, v: list[float], vnorm: float) -> float:
    return sum(a * b for a, b in zip(q, v)) / (qnorm * vnorm)


def search(query: str, k: int = 4) -> list[dict]:
    idx = _index()
    chunks = idx["chunks"]
    if not chunks:
        return []
    q = gemini.embed(query, task_type="RETRIEVAL_QUERY")
    qnorm = math.sqrt(sum(x * x for x in q)) or 1.0
    scored = [
        {"cite": c["cite"], "page": c["page"], "text": c["text"],
         "score": round(_cosine(q, qnorm, c["embedding"], c["_norm"]), 4)}
        for c in chunks
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]
