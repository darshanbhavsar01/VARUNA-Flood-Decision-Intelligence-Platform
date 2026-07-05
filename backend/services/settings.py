"""Central settings + city-config loading for the VARUNA backend.

Reads .env (local dev) or real env vars (Cloud Run). Nothing city-specific is
hardcoded; city behaviour comes from configs/<city>.yaml (§7).
"""
from __future__ import annotations

import functools
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO = Path(__file__).resolve().parents[2]
CONFIGS = REPO / "configs"

load_dotenv(REPO / ".env")   # no-op on Cloud Run (file absent); env vars win


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    gemini_api_key: str = ""
    # Backup AI-Studio keys (comma-separated). When every model is exhausted on the
    # primary key, the whole model chain is retried on each backup key in turn —
    # each key is a separate account with its own quota.
    gemini_backup_keys: str = ""
    # Ordered fallback chain: on quota (429) or missing model (404) we advance to
    # the next. Each model has its own free-tier quota bucket, so this multiplies
    # effective capacity. Comma-separated; edit via GEMINI_MODELS env var.
    gemini_models: str = (
        "gemini-2.5-flash,gemini-flash-latest,gemini-2.0-flash,"
        "gemini-2.5-flash-lite,gemini-2.0-flash-lite,gemini-flash-lite-latest"
    )
    gemini_model: str = ""   # legacy single-model override; prepended if set
    agent_model: str = "gemini-2.5-flash"   # ADK agents (single model; has quota)

    @property
    def gemini_api_keys(self) -> list[str]:
        """Primary key first, then backup keys (deduped, non-empty)."""
        raw = [self.gemini_api_key] + [
            k.strip() for k in self.gemini_backup_keys.split(",")]
        seen, out = set(), []
        for k in raw:
            k = (k or "").strip()
            if k and k not in seen:
                seen.add(k)
                out.append(k)
        return out

    @property
    def gemini_model_chain(self) -> list[str]:
        raw = [m.strip() for m in
               ((self.gemini_model + "," if self.gemini_model else "")
                + self.gemini_models).split(",")]
        seen, out = set(), []
        for m in raw:
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return out
    google_cloud_project: str = ""
    bq_dataset: str = "varuna"
    bq_location: str = "asia-south1"
    default_city: str = "blr"


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()


@functools.lru_cache
def _config_files() -> dict[str, Path]:
    """Map city_id -> config path by reading each yaml's city_id."""
    out = {}
    for p in CONFIGS.glob("*.yaml"):
        try:
            cid = yaml.safe_load(p.read_text(encoding="utf-8")).get("city_id")
            if cid:
                out[cid] = p
        except Exception:  # noqa: BLE001
            continue
    return out


@functools.lru_cache
def get_city_config(city_id: str) -> dict:
    files = _config_files()
    if city_id not in files:
        raise KeyError(f"Unknown city_id '{city_id}'. Known: {sorted(files)}")
    return yaml.safe_load(files[city_id].read_text(encoding="utf-8"))


def list_cities() -> list[dict]:
    cities = []
    for cid, p in sorted(_config_files().items()):
        c = yaml.safe_load(p.read_text(encoding="utf-8"))
        cities.append({"city_id": cid, "name": c.get("name", cid),
                       "mode": c.get("mode", "full"), "bbox": c.get("bbox")})
    return cities
