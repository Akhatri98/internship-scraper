"""Environment / configuration loading.

All secrets live in .env (gitignored). This module is the single place that
reads them so the rest of the code never touches os.environ directly.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# .env sits at the repo root (one level above this package).
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")  # only used by the Stage 3 seed


def require(name: str) -> str:
    """Return an env var or raise a clear error if it's missing/empty."""
    val = os.environ.get(name, "")
    if not val:
        raise RuntimeError(f"Missing required env var: {name} (expected in {_ENV_PATH})")
    return val
