"""Ask AI export — tara raporu sarmalayıcı."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import AI_EXPORTS_DIR
from src.tara_export import copy_tara_to_clipboard, render_tara_markdown, write_tara_export


def build_ask_ai_section(processed_payload: dict[str, Any], nickname: str) -> dict[str, Any]:
    content = render_tara_markdown(nickname, processed_payload)
    return {
        "export_path": str(AI_EXPORTS_DIR / f"{nickname.lower()}_tara_latest.md"),
        "preview_lines": content.splitlines()[:20],
        "full_content": content,
    }


def write_ask_ai_export(
    nickname: str,
    processed_payload: dict[str, Any],
    export_dir: Path | None = None,
    *,
    demo_note: str | None = None,
) -> Path:
    return write_tara_export(nickname, processed_payload, export_dir, demo_note=demo_note)


def render_ask_ai_markdown(section: dict[str, Any]) -> list[str]:
    return [
        "## Ask AI",
        "",
        f"ChatGPT export: `{section.get('export_path', 'unavailable')}`",
        "",
        "_Tam içerik `jurses_tara_latest.md` dosyasındadır; raw debug dahil değildir._",
        "",
    ]
