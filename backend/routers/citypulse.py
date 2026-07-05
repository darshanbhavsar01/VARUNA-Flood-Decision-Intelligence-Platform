"""CityPulse — conversational analytics over 5+ years of grievances (§4 P0, §9).

POST /api/citypulse/chat {question} ->
  { ok, sql, columns, rows, chart, narrative, bytes_scanned }
NL -> SQL (guarded) -> execute -> auto-pick chart -> Gemini narrative.
Every LLM step degrades gracefully to a readable fallback (§13).
"""
from __future__ import annotations

import datetime as dt
import re

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from ..services import gemini, nl2sql

router = APIRouter(prefix="/api/citypulse", tags=["citypulse"])

DATEISH = re.compile(r"(month|date|day|week|year|ts|time)", re.I)


class ChatIn(BaseModel):
    question: str


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def pick_chart(columns: list[str], rows: list[dict]) -> dict:
    """Heuristic chart spec from result shape. type ∈ line|bar|pie|none."""
    if not rows or len(columns) < 2:
        return {"type": "none"}
    num_cols = [c for c in columns if all(_is_number(r[c]) or r[c] is None for r in rows)]
    cat_cols = [c for c in columns if c not in num_cols]
    if not num_cols or not cat_cols:
        return {"type": "none"}
    x, y = cat_cols[0], num_cols[0]
    if DATEISH.search(x):
        return {"type": "line", "x": x, "y": y}
    if len(rows) <= 6:
        return {"type": "pie", "x": x, "y": y}
    return {"type": "bar", "x": x, "y": y}


def _rows_preview(columns, rows, limit=20) -> str:
    head = rows[:limit]
    lines = [" | ".join(columns)]
    for r in head:
        lines.append(" | ".join(str(r.get(c)) for c in columns))
    more = "" if len(rows) <= limit else f"\n(+{len(rows)-limit} more rows)"
    return "\n".join(lines) + more


def narrate(question: str, columns, rows) -> str:
    if not rows:
        return "No rows matched that question."
    try:
        prompt = (
            f"Question: {question}\n\nQuery result ({len(rows)} rows):\n"
            f"{_rows_preview(columns, rows)}\n\n"
            "Write ONE concise, factual paragraph (<=3 sentences) answering the "
            "question from this result. Cite specific numbers. No preamble.")
        return gemini.generate(prompt, temperature=0.3)
    except gemini.GeminiError:
        # graceful fallback: state the headline number
        first = rows[0]
        return (f"Returned {len(rows)} row(s). Top result: "
                + ", ".join(f"{k}={first[k]}" for k in columns) + ".")


@router.post("/chat")
def chat(body: ChatIn):
    q = body.question.strip()
    if not q:
        return {"ok": False, "error": "empty question"}
    try:
        result = nl2sql.run(q)
    except gemini.GeminiRateLimited:
        return {"ok": False, "rate_limited": True, "rows": [], "columns": [],
                "narrative": "The AI is momentarily rate-limited (Gemini free tier). "
                             "Please try again in a few seconds."}
    except gemini.GeminiError as e:
        return {"ok": False, "error": f"LLM unavailable: {e}", "rows": [], "columns": [],
                "narrative": "The AI service is temporarily unavailable."}

    if not result["ok"]:
        return {"ok": False, "sql": result.get("sql"),
                "error": result["error"], "rows": [], "columns": [],
                "narrative": "I couldn't turn that into a safe query. "
                             "Try rephrasing, e.g. 'top wards by waterlogging in 2024'."}

    rows = jsonable_encoder(result["rows"])          # datetime/Decimal -> JSON-safe
    columns = result["columns"]
    return {
        "ok": True, "question": q, "sql": result["sql"],
        "columns": columns, "rows": rows, "row_count": len(rows),
        "chart": pick_chart(columns, rows),
        "narrative": narrate(q, columns, result["rows"]),
        "bytes_scanned": result["bytes_scanned"],
    }
