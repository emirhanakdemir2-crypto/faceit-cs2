from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.config import MISSING_DATA_LABEL

DEMO_EXTENSIONS = (".dem", ".dem.gz", ".dem.zst")
MATCH_ID_RE = re.compile(r"1-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

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


def _extract_match_id_from_name(filename: str) -> str | None:
    match = MATCH_ID_RE.search(filename)
    return match.group(0) if match else None


def scan_demo_folder(folder: Path, known_match_ids: set[str] | None = None) -> dict[str, Any]:
    """Demo klasörünü tarar; parser olmadan liste ve eşleştirme döner."""
    if not folder.exists():
        return {
            "folder": str(folder),
            "found": False,
            "message": f"Demo klasörü bulunamadı: {folder}",
            "files": [],
            "matched": [],
            "unmatched": [],
            "parser_available": _demoparser_available(),
            "mechanics": {},
            "target_metrics": _target_metrics_template(),
        }

    files: list[dict[str, Any]] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        name_lower = path.name.lower()
        if not any(name_lower.endswith(ext) for ext in DEMO_EXTENSIONS):
            continue
        match_id = _extract_match_id_from_name(path.name)
        entry = {
            "filename": path.name,
            "path": str(path),
            "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
            "match_id": match_id or MISSING_DATA_LABEL,
        }
        files.append(entry)

    known = known_match_ids or set()
    matched = [f for f in files if f["match_id"] in known]
    unmatched = [f for f in files if f["match_id"] == MISSING_DATA_LABEL or f["match_id"] not in known]

    result: dict[str, Any] = {
        "folder": str(folder.resolve()),
        "found": True,
        "message": f"{len(files)} demo dosyası bulundu.",
        "files": files,
        "matched": matched,
        "unmatched": unmatched,
        "parser_available": _demoparser_available(),
        "mechanics": {},
        "target_metrics": _target_metrics_template(),
    }

    if result["parser_available"] and files:
        result["mechanics"] = _try_parse_demos(files[:3])
    elif files and not result["parser_available"]:
        result["message"] += " Demo analizi için demoparser2 kurulmalı."

    return result


def _demoparser_available() -> bool:
    try:
        import demoparser2  # noqa: F401

        return True
    except ImportError:
        return False


def _target_metrics_template() -> list[dict[str, str]]:
    return [
        {"key": key, "label": label, "value": MISSING_DATA_LABEL, "source": "demo gerekli"}
        for key, label in MECHANICAL_TARGET_METRICS
    ]


def _try_parse_demos(files: list[dict[str, Any]]) -> dict[str, Any]:
    """demoparser2 ile ilk basit mekanik metrikleri çıkarmayı dener."""
    try:
        import demoparser2
    except ImportError:
        return {"available": False, "message": "demoparser2 kurulu değil."}

    aggregated: dict[str, Any] = {
        "available": True,
        "demos_parsed": 0,
        "avg_speed_at_shot": MISSING_DATA_LABEL,
        "shots_while_moving_pct": MISSING_DATA_LABEL,
        "weapon_shot_counts": {},
        "note": "",
    }

    speeds: list[float] = []
    moving_shots = 0
    total_shots = 0
    weapon_counts: dict[str, int] = {}

    for demo in files:
        path = demo.get("path")
        if not path:
            continue
        try:
            events = demoparser2.parse_events(path, player=["X", "Y", "Z", "velocity"], other=["weapon"])
            aggregated["demos_parsed"] += 1
            for _name, payload in events:
                if not isinstance(payload, list):
                    continue
                for row in payload:
                    if not isinstance(row, dict):
                        continue
                    vel = row.get("velocity")
                    if isinstance(vel, (list, tuple)) and len(vel) >= 2:
                        speed = (float(vel[0]) ** 2 + float(vel[1]) ** 2) ** 0.5
                        speeds.append(speed)
                        if speed > 34:
                            moving_shots += 1
                        total_shots += 1
                    weapon = row.get("weapon")
                    if weapon:
                        weapon_counts[str(weapon)] = weapon_counts.get(str(weapon), 0) + 1
        except Exception:
            continue

    if speeds:
        aggregated["avg_speed_at_shot"] = round(sum(speeds) / len(speeds), 1)
    if total_shots > 0:
        aggregated["shots_while_moving_pct"] = round(moving_shots / total_shots * 100, 1)
    if weapon_counts:
        aggregated["weapon_shot_counts"] = weapon_counts

    if aggregated["demos_parsed"] == 0:
        aggregated["note"] = (
            "Demo dosyaları bulundu ancak güvenilir mekanik metrik çıkarılamadı. "
            "Parser sürümü veya demo formatı uyumsuz olabilir."
        )
    else:
        aggregated["note"] = (
            f"{aggregated['demos_parsed']} demo üzerinden ilk basit metrikler çıkarıldı. "
            "Counter-strafe/spray skorları için daha gelişmiş pipeline gerekir."
        )

    return aggregated
