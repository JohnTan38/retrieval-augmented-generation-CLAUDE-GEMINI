"""Local-only API entrypoint that loads developer environment files."""

from pathlib import Path

from dotenv import load_dotenv


_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT / ".env.local")

from backend.app import create_app  # noqa: E402


app = create_app()
