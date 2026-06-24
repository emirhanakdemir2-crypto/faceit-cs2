from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = DATA_DIR / "reports"
DB_DIR = DATA_DIR / "db"
DB_PATH = DB_DIR / "coach.sqlite"
MATCHES_RAW_DIR = RAW_DIR / "matches"

FACEIT_BASE_URL = "https://open.faceit.com/data/v4"
GAME_ID = "cs2"
DEFAULT_MATCH_COUNT = 20

MISSING_DATA_LABEL = "veri eksik"


def load_config() -> None:
    """Load environment variables from .env at project root."""
    load_dotenv(PROJECT_ROOT / ".env")


def get_api_key() -> str:
    load_config()
    key = os.getenv("FACEIT_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "FACEIT_API_KEY bulunamadı. .env dosyasına anahtarınızı ekleyin "
            "(bkz. .env.example)."
        )
    return key


def ensure_data_dirs() -> None:
    for directory in (RAW_DIR, PROCESSED_DIR, REPORTS_DIR, MATCHES_RAW_DIR, DB_DIR):
        directory.mkdir(parents=True, exist_ok=True)
