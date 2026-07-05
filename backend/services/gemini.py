"""Gemini client wrapper (google-genai, AI Studio key — NOT Vertex endpoints, §6).

Model-fallback chain: each Gemini model has its own free-tier quota bucket, so when
one returns 429 (exhausted) — or 404 (model doesn't exist) — we advance to the next
model in the configured chain and stick with whatever works. This multiplies our
effective quota and keeps CityPulse/Vision alive during a demo. Only when EVERY
model in the chain is exhausted do we surface GeminiRateLimited (a clean,
retry-later message). Configure the chain via GEMINI_MODELS (see settings).
"""
from __future__ import annotations

import functools
import json
import threading

from .settings import get_settings


class GeminiError(RuntimeError):
    pass


class GeminiRateLimited(GeminiError):
    """Every model in the chain is quota-exhausted — caller shows 'try again'."""


def _is_429(exc) -> bool:
    s = str(exc)
    return "429" in s or "RESOURCE_EXHAUSTED" in s or "quota" in s.lower()


def _is_missing(exc) -> bool:
    s = str(exc).lower()
    return "404" in s or "not_found" in s or "not found" in s


def _skippable(exc) -> bool:
    return _is_429(exc) or _is_missing(exc)


@functools.lru_cache
def _client():
    s = get_settings()
    if not s.gemini_api_key:
        raise GeminiError("GEMINI_API_KEY not configured")
    from google import genai
    return genai.Client(api_key=s.gemini_api_key)


# Persistent cursor: once a model works we keep using it until IT exhausts, then
# advance. Wraps around so recovered models get retried on the next full cycle.
_cursor = 0
_cursor_lock = threading.Lock()
_last_model = None


def active_model() -> str | None:
    return _last_model


def _run(call):
    """Try `call(model)` across the chain starting at the cursor; return first
    success. Skip 429/404 models. Raise GeminiRateLimited if all are exhausted."""
    global _cursor, _last_model
    chain = get_settings().gemini_model_chain
    if not chain:
        raise GeminiError("no Gemini models configured")
    n = len(chain)
    start = _cursor % n
    exhausted = []
    for i in range(n):
        idx = (start + i) % n
        model = chain[idx]
        try:
            result = call(model)
            with _cursor_lock:
                _cursor = idx
            _last_model = model
            return result
        except GeminiError:
            raise
        except Exception as e:  # noqa: BLE001
            if _skippable(e):
                exhausted.append(model)
                continue
            raise GeminiError(f"{model}: {e}") from e
    raise GeminiRateLimited(
        "all Gemini models exhausted: " + ", ".join(exhausted))


def generate(prompt: str, system: str | None = None,
             temperature: float = 0.2, as_json: bool = False) -> str:
    from google.genai import types
    cfg = types.GenerateContentConfig(
        temperature=temperature,
        system_instruction=system,
        response_mime_type="application/json" if as_json else None,
    )

    def call(model):
        r = _client().models.generate_content(model=model, contents=prompt, config=cfg)
        return (r.text or "").strip()

    return _run(call)


def generate_json(prompt: str, system: str | None = None,
                  temperature: float = 0.2) -> dict:
    return _parse_json(generate(prompt, system=system, temperature=temperature,
                                as_json=True))


def analyze_image(image_bytes: bytes, mime_type: str, prompt: str,
                  temperature: float = 0.1) -> dict:
    """Gemini Vision -> structured JSON, across the model-fallback chain."""
    from google.genai import types
    cfg = types.GenerateContentConfig(
        temperature=temperature, response_mime_type="application/json")

    def call(model):
        r = _client().models.generate_content(
            model=model,
            contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                      prompt],
            config=cfg)
        return _parse_json((r.text or "").strip())

    return _run(call)


EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768


def embed(text: str, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
    """Single-text embedding (matches the SOP index: gemini-embedding-001, 768d)."""
    from google.genai import types
    cfg = types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBED_DIM)
    try:
        r = _client().models.embed_content(model=EMBED_MODEL, contents=text, config=cfg)
        return list(r.embeddings[0].values)
    except Exception as e:  # noqa: BLE001
        raise (GeminiRateLimited if _is_429(e) else GeminiError)(str(e)) from e


def _parse_json(txt: str) -> dict:
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        s, e = txt.find("{"), txt.rfind("}")   # salvage object from prose/fences
        if s != -1 and e != -1:
            return json.loads(txt[s:e + 1])
        raise GeminiError(f"Non-JSON response: {txt[:200]}")
