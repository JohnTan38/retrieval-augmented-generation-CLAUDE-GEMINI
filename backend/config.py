"""Server-only, lazy configuration for the RAG gateway."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ARTIFACT = Path("data") / "index" / "swk501-v1.json.gz"


class ConfigurationUnavailable(RuntimeError):
    """Raised without exposing the missing configuration value."""


@dataclass(frozen=True)
class Settings:
    artifact_path: Path
    api_key: str | None
    embedding_timeout_seconds: float = 5.0
    generation_timeout_seconds: float = 25.0
    total_timeout_seconds: float = 30.0


def get_settings() -> Settings:
    """Read only server environment values when the gateway needs them."""
    try:
        import dotenv
        dotenv.load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        dotenv.load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")
        dotenv.load_dotenv()
    except Exception:
        pass
    raw_path = os.environ.get("RAG_INDEX_PATH")
    artifact_path = Path(raw_path) if raw_path else DEFAULT_ARTIFACT
    key = os.environ.get("GEMINI_API_KEY")
    return Settings(artifact_path=artifact_path, api_key=key.strip() if key and key.strip() else None)


def require_api_key(settings: Settings) -> str:
    if not settings.api_key:
        raise ConfigurationUnavailable("generation credentials are unavailable")
    return settings.api_key
