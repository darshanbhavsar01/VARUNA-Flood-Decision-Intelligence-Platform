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
    gemini_model: str = "gemini-flash-latest"
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
