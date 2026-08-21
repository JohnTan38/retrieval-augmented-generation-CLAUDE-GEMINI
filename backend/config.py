"""Server-only, lazy configuration for the RAG gateway."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ARTIFACT = Path("data") / "index" / "swk501-v2.json.gz"
DEFAULT_GENERATION_MODEL = "gemini-3.7-flash"


class ConfigurationUnavailable(RuntimeError):
    """Raised without exposing the missing configuration value."""


@dataclass(frozen=True)
class Settings:
    artifact_path: Path
    api_key: str | None
    generation_model: str = DEFAULT_GENERATION_MODEL
    embedding_timeout_seconds: float = 5.0
    generation_timeout_seconds: float = 25.0
    total_timeout_seconds: float = 30.0


def get_settings() -> Settings:
    """Read only server environment values when the gateway needs them."""
    raw_path = os.environ.get("RAG_INDEX_PATH")
    artifact_path = Path(raw_path) if raw_path else DEFAULT_ARTIFACT
    key = os.environ.get("GEMINI_API_KEY")
    generation_model = os.environ.get("GEMINI_GENERATION_MODEL", "").strip() or DEFAULT_GENERATION_MODEL
    return Settings(artifact_path=artifact_path, api_key=key.strip() if key and key.strip() else None, generation_model=generation_model)


def require_api_key(settings: Settings) -> str:
    if not settings.api_key:
        raise ConfigurationUnavailable("generation credentials are unavailable")
    return settings.api_key
