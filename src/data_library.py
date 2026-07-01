from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import (
    AI_EXPORTS_DIR,
    DB_PATH,
    DEMOS_DIR,
    PROCESSED_DIR,
    RAW_DIR,
    REPORTS_DIR,
)
from src.suite_common import SOURCE_FACEIT, fmt_simple, metric


def analyze_data_library(
    nickname: str,
    memory: dict[str, Any] | None,
) -> dict[str, Any]:
    def count_files(folder: Path, pattern: str = "*") -> int:
        if not folder.exists():
            return 0
        return sum(1 for p in folder.glob(pattern) if p.is_file())

    raw_count = count_files(RAW_DIR / "matches", "*.json")
    processed_count = count_files(PROCESSED_DIR, "*.json")
    demo_count = count_files(DEMOS_DIR)
    report_count = count_files(REPORTS_DIR, "*.md")
    export_count = count_files(AI_EXPORTS_DIR, "*.md")

    return {
        "raw_faceit_files": metric(raw_count, source=SOURCE_FACEIT),
        "processed_files": metric(processed_count, source=SOURCE_FACEIT),
        "demo_files": metric(demo_count, source=SOURCE_FACEIT),
        "report_files": metric(report_count, source=SOURCE_FACEIT),
        "ai_exports": metric(export_count, source=SOURCE_FACEIT),
        "database": metric("data/db/coach.sqlite", source=SOURCE_FACEIT),
        "last_analysis": metric(
            (memory or {}).get("previous_analysis_date") or "first run",
            source=SOURCE_FACEIT,
        ),
        "api_key": metric("hidden", source=SOURCE_FACEIT, confidence="none"),
        "env": metric("hidden", source=SOURCE_FACEIT, confidence="none"),
        "nickname": metric(nickname, source=SOURCE_FACEIT),
    }


def render_data_library_markdown(section: dict[str, Any]) -> list[str]:
    lines = [
        "## Data Library",
        "",
        f"- Raw FACEIT files: {fmt_simple(section.get('raw_faceit_files'))}",
        f"- Processed files: {fmt_simple(section.get('processed_files'))}",
        f"- Demo files: {fmt_simple(section.get('demo_files'))}",
        f"- Report files: {fmt_simple(section.get('report_files'))}",
        f"- AI exports: {fmt_simple(section.get('ai_exports'))}",
        f"- Database: {fmt_simple(section.get('database'))}",
        f"- Last analysis: {fmt_simple(section.get('last_analysis'))}",
        f"- API key / .env: hidden (not exported)",
        "",
    ]
    return lines
