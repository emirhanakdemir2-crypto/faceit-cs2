from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import MISSING_DATA_LABEL
from src.demo_parser import demoparser_available, find_demo_files

MECHANICAL_TARGET_METRICS = [
    ("shots_while_moving_pct", "Shots while moving %"),
    ("first_bullet_moving_pct", "First bullet moving %"),
    ("avg_speed_at_shot", "Average speed at shot"),
    ("stop_to_shot_timing_ms", "Stop-to-shot timing"),
    ("spray_length_avg", "Spray length average"),
    ("first_5_bullet_control", "First 5 bullet control score"),
    ("ak_spray_note", "AK spray kontrol notu"),
    ("m4_spray_note", "M4 spray kontrol notu"),
]


def scan_demo_folder(folder: Path, known_match_ids: set[str] | None = None) -> dict[str, Any]:
    """Demo klasörünü tarar; parse etmez (--mechanics ile ayrı çalışır)."""
    if not folder.exists():
        return {
            "folder": str(folder),
            "found": False,
            "message": f"Demo klasörü bulunamadı: {folder}",
            "files": [],
            "matched": [],
            "unmatched": [],
            "compressed": [],
            "parser_available": demoparser_available(),
            "mechanics": {},
            "target_metrics": _target_metrics_template(),
        }

    raw_files = find_demo_files(folder)
    files = [
        {
            "filename": f["filename"],
            "path": f["path"],
            "size_mb": f["size_mb"],
            "match_id": f["match_id"],
            "compressed": f.get("compressed", False),
            "parseable": f.get("parseable", False),
        }
        for f in raw_files
    ]

    known = known_match_ids or set()
    matched = [f for f in files if f["match_id"] in known]
    unmatched = [
        f for f in files
        if f["match_id"] == MISSING_DATA_LABEL or f["match_id"] not in known
    ]
    compressed = [f for f in files if f.get("compressed")]

    message = f"{len(files)} demo dosyası bulundu."
    if not files:
        message = "Demo klasörü boş."
    elif compressed and not any(f.get("parseable") for f in files):
        message += " Sıkıştırılmış demo bulundu; önce .dem olarak çıkarılmalı."
    elif files and not demoparser_available():
        message += " Mekanik analiz için: pip install demoparser2 ve --mechanics kullanın."

    return {
        "folder": str(folder.resolve()),
        "found": len(files) > 0,
        "message": message,
        "files": files,
        "matched": matched,
        "unmatched": unmatched,
        "compressed": compressed,
        "parser_available": demoparser_available(),
        "mechanics": {},
        "target_metrics": _target_metrics_template(),
    }


def _target_metrics_template() -> list[dict[str, str]]:
    return [
        {"key": key, "label": label, "value": MISSING_DATA_LABEL, "source": "demo + --mechanics"}
        for key, label in MECHANICAL_TARGET_METRICS
    ]
