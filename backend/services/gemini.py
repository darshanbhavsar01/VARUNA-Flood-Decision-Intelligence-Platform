"""Gemini client wrapper (google-genai, AI Studio key — NOT Vertex endpoints, §6).

Every LLM feature degrades gracefully: callers catch GeminiError and show a
readable fallback rather than a blank screen (§13).
"""
from __future__ import annotations

import functools
import json

from .settings import get_settings


class GeminiError(RuntimeError):
    pass


@functools.lru_cache
def _client():
    s = get_settings()
    if not s.gemini_api_key:
        raise GeminiError("GEMINI_API_KEY not configured")
    from google import genai
    return genai.Client(api_key=s.gemini_api_key)


def generate(prompt: str, system: str | None = None,
             temperature: float = 0.2, as_json: bool = False) -> str:
    """Single-shot generation. Returns raw text (or JSON string if as_json)."""
    from google.genai import types
    cfg = types.GenerateContentConfig(
        temperature=temperature,
        system_instruction=system,
        response_mime_type="application/json" if as_json else None,
    )
    try:
        r = _client().models.generate_content(
            model=get_settings().gemini_model, contents=prompt, config=cfg)
        return (r.text or "").strip()
    except Exception as e:  # noqa: BLE001
        raise GeminiError(str(e)) from e


def generate_json(prompt: str, system: str | None = None,
                  temperature: float = 0.2) -> dict:
    txt = generate(prompt, system=system, temperature=temperature, as_json=True)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        # models occasionally wrap JSON in prose/fences; salvage the object
        s, e = txt.find("{"), txt.rfind("}")
        if s != -1 and e != -1:
            return json.loads(txt[s:e + 1])
        raise GeminiError(f"Non-JSON response: {txt[:200]}")
