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


def _is_bad_key(exc) -> bool:
    s = str(exc).lower()
    return ("api key not valid" in s or "api_key_invalid" in s
            or "invalid api key" in s or "401" in s or "unauthenticated" in s
            or "permission_denied" in s or "403" in s)


def _skippable(exc) -> bool:
    # quota, transient overload, missing model, or a dead/invalid key -> try next
    s = str(exc).lower()
    return (_is_429(exc) or _is_missing(exc) or _is_bad_key(exc)
            or "503" in s or "unavailable" in s or "overloaded" in s)


@functools.lru_cache
def _client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


def _attempts() -> list[tuple[str, str]]:
    """Flat (api_key, model) attempt order: exhaust the primary key's whole model
    chain before moving to the next (backup) key."""
    s = get_settings()
    keys = s.gemini_api_keys
    if not keys:
        raise GeminiError("GEMINI_API_KEY not configured")
    chain = s.gemini_model_chain
    if not chain:
        raise GeminiError("no Gemini models configured")
    return [(k, m) for k in keys for m in chain]


# Persistent cursor over the (key, model) attempt list: once one works we keep
# using it until it exhausts, then advance. Wraps around so recovered
# keys/models are retried on the next cycle.
_cursor = 0
_cursor_lock = threading.Lock()
_last_model = None
_last_key_index = 0


def active_model() -> str | None:
    return _last_model


def active_key_index() -> int:
    return _last_key_index


def _run(call):
    """Try `call(client, model)` across every (key, model) starting at the cursor;
    return the first success. Skip 429/503/404. Raise GeminiRateLimited only when
    ALL keys x models are exhausted."""
    global _cursor, _last_model, _last_key_index
    attempts = _attempts()
    keys = get_settings().gemini_api_keys
    n = len(attempts)
    start = _cursor % n
    exhausted = []
    for i in range(n):
        idx = (start + i) % n
        api_key, model = attempts[idx]
        try:
            result = call(_client(api_key), model)
            with _cursor_lock:
                _cursor = idx
            _last_model = model
            _last_key_index = keys.index(api_key)
            return result
        except GeminiError:
            raise
        except Exception as e:  # noqa: BLE001
            if _skippable(e):
                exhausted.append(f"key{keys.index(api_key)}:{model}")
                continue
            raise GeminiError(f"{model}: {e}") from e
    raise GeminiRateLimited("all Gemini keys x models exhausted: "
                            + ", ".join(exhausted))


def generate(prompt: str, system: str | None = None,
             temperature: float = 0.2, as_json: bool = False) -> str:
    from google.genai import types
    cfg = types.GenerateContentConfig(
        temperature=temperature,
        system_instruction=system,
        response_mime_type="application/json" if as_json else None,
    )

    def call(client, model):
        r = client.models.generate_content(model=model, contents=prompt, config=cfg)
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

    def call(client, model):
        r = client.models.generate_content(
            model=model,
            contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                      prompt],
            config=cfg)
        return _parse_json((r.text or "").strip())

    return _run(call)


EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768


def embed(text: str, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
    """Single-text embedding (matches the SOP index: gemini-embedding-001, 768d).
    Tries each API key on quota (429) — one embedding model, multiple key buckets."""
    from google.genai import types
    cfg = types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBED_DIM)
    keys = get_settings().gemini_api_keys
    last = None
    for api_key in keys:
        try:
            r = _client(api_key).models.embed_content(
                model=EMBED_MODEL, contents=text, config=cfg)
            return list(r.embeddings[0].values)
        except Exception as e:  # noqa: BLE001
            last = e
            if _skippable(e):
                continue
            raise GeminiError(str(e)) from e
    raise (GeminiRateLimited if _is_429(last) else GeminiError)(str(last))


def _parse_json(txt: str) -> dict:
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        s, e = txt.find("{"), txt.rfind("}")   # salvage object from prose/fences
        if s != -1 and e != -1:
            return json.loads(txt[s:e + 1])
        raise GeminiError(f"Non-JSON response: {txt[:200]}")
