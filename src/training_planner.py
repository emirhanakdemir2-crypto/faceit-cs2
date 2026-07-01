from __future__ import annotations

from typing import Any

from src import suite_config as cfg
from src.suite_common import SOURCE_DERIVED, as_float, fmt_simple, metric


def analyze_training(
    focus_areas: list[dict[str, Any]],
    map_stats: dict[str, Any],
    mech: dict[str, Any],
) -> dict[str, Any]:
    ak = mech.get("ak_metrics") or {}
    m4 = mech.get("m4_metrics") or {}
    ak_f = as_float(ak.get("first_bullet_moving_pct"))
    m4_l = as_float(m4.get("long_spray_pct"))
    sp_f = as_float(mech.get("starter_pistol_first_bullet_moving_pct"))
    ak_bad = ak_f is not None and ak_f > cfg.FOCUS_AK_FIRST_BULLET
    m4_bad = m4_l is not None and m4_l > cfg.FOCUS_M4_LONG_SPRAY
    pistol_bad = sp_f is not None and sp_f > cfg.FOCUS_STARTER_PISTOL_FIRST
    weak_map = map_stats.get("worst_map")

    daily = [
        "5 dk AK counter-strafe" if ak_bad else "5 dk rifle warmup taps",
        "5 dk M4 burst/reset" if m4_bad else "5 dk spray control drill",
        "5 dk USP/Glock stop-shot" if pistol_bad else "5 dk pistol movement drill",
        "1 demo review checklist",
    ]

    weekly = [
        "Gün 1: AK counter-strafe + 1–3 bullet",
        "Gün 2: M4 5 bullet burst + spray reset",
        "Gün 3: Pistol mechanics",
        f"Gün 4: {weak_map or 'weak map'} review" if weak_map else "Gün 4: Map position review",
        "Gün 5: Demo review + utility defaults",
        "Gün 6: 1–2 FACEIT + demo çıkar",
        "Gün 7: Metric comparison (Mechanics Lab)",
    ]

    if focus_areas:
        fa = focus_areas[0]
        weekly[0] = f"Gün 1: {fa.get('drill', weekly[0])}"

    return {
        "daily": [metric(d, source=SOURCE_DERIVED) for d in daily],
        "weekly": [metric(w, source=SOURCE_DERIVED) for w in weekly],
    }


def render_training_markdown(section: dict[str, Any]) -> list[str]:
    lines = ["## Training Plan", "", "### Günlük", ""]
    for d in section.get("daily") or []:
        lines.append(f"- {fmt_simple(d)}")
    lines.extend(["", "### Haftalık", ""])
    for w in section.get("weekly") or []:
        lines.append(f"- {fmt_simple(w)}")
    lines.append("")
    return lines
