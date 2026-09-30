"""Runtime settings, read from environment variables.

DATABASE_URL defaults to a local SQLite file; point it at PostgreSQL (Supabase / Neon)
with e.g. postgresql+psycopg://user:pass@host/db and nothing else changes.
"""

import os
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'justiceflow.db'}")
SECRET_KEY = os.getenv("JF_SECRET_KEY", "dev-only-insecure-key-change-me-before-any-pilot")
TOKEN_TTL_MINUTES = int(os.getenv("JF_TOKEN_TTL_MINUTES", "480"))
MODEL_DIR = Path(os.getenv("JF_MODEL_DIR", BASE_DIR / "model_store"))
CORS_ORIGINS = os.getenv("JF_CORS_ORIGINS", "http://localhost:5173").split(",")


def today() -> date:
    """The system's notion of 'today'. JF_AS_OF pins it for demos and tests."""
    pinned = os.getenv("JF_AS_OF")
    return date.fromisoformat(pinned) if pinned else date.today()
