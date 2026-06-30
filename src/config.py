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
AI_EXPORTS_DIR = DATA_DIR / "ai_exports"
DEMOS_DIR = DATA_DIR / "demos"

FACEIT_BASE_URL = "https://open.faceit.com/data/v4"
GAME_ID = "cs2"
DEFAULT_MATCH_COUNT = 120
DEFAULT_DAYS = 90
DEFAULT_SESSION_RECENT = 10
MAX_MATCH_COUNT = 200
SHORT_FORM_MATCH_COUNT = 5

MISSING_DATA_LABEL = "veri eksik"
GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"


def load_config() -> None:
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


def get_gemini_api_key() -> str:
    load_config()
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "GEMINI_API_KEY bulunamadı. .env dosyasına anahtarınızı ekleyin "
            "(bkz. .env.example). --ai kullanmak için gereklidir."
        )
    return key


def ensure_data_dirs() -> None:
    for directory in (
        RAW_DIR,
        PROCESSED_DIR,
        REPORTS_DIR,
        MATCHES_RAW_DIR,
        DB_DIR,
        AI_EXPORTS_DIR,
        DEMOS_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
