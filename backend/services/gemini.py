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
    return _parse_json(txt)


def analyze_image(image_bytes: bytes, mime_type: str, prompt: str,
                  temperature: float = 0.1) -> dict:
    """Gemini Vision -> structured JSON. Used by the citizen photo-report flow."""
    from google.genai import types
    cfg = types.GenerateContentConfig(
        temperature=temperature, response_mime_type="application/json")
    try:
        r = _client().models.generate_content(
            model=get_settings().gemini_model,
            contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                      prompt],
            config=cfg)
        return _parse_json((r.text or "").strip())
    except GeminiError:
        raise
    except Exception as e:  # noqa: BLE001
        raise GeminiError(str(e)) from e


def _parse_json(txt: str) -> dict:
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        s, e = txt.find("{"), txt.rfind("}")   # salvage object from prose/fences
        if s != -1 and e != -1:
            return json.loads(txt[s:e + 1])
        raise GeminiError(f"Non-JSON response: {txt[:200]}")
