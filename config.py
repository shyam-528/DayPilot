"""DayPilot settings loaded from .env.

The bot token is NEVER hardcoded. Copy .env.example to .env and fill it in.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _int_env(name: str, default: int = 0) -> int:
    """Read an integer from the environment without crashing on a typo."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ALLOWED_USER_ID = _int_env("ALLOWED_USER_ID", 0)
CITY = os.getenv("CITY", "Kolkata").strip() or "Kolkata"
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata").strip() or "Asia/Kolkata"

_db_path = os.getenv("DB_PATH", "").strip()
DB_PATH = _db_path or str(BASE_DIR / "data" / "daypilot.db")
