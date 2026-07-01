from __future__ import annotations

from typing import Any

from src import suite_config as cfg
from src.suite_common import SOURCE_DERIVED, SOURCE_DEMO, as_float, fmt_simple, metric


def analyze_operation(
    mechanics_lab: dict[str, Any] | None,
    mech: dict[str, Any],
    map_stats: dict[str, Any],
) -> dict[str, Any]:
    parsed = (mechanics_lab or {}).get("parsed_count") or 0
    ak_f = as_float((mech.get("ak_metrics") or {}).get("first_bullet_moving_pct"))
    m4_l = as_float((mech.get("m4_metrics") or {}).get("long_spray_pct"))
    sp = as_float(mech.get("starter_pistol_first_bullet_moving_pct"))
    weak = map_stats.get("worst_map")

    missions = [
        {
            "name": "3 demo analiz et",
            "status": _status(parsed >= 3, parsed > 0, parsed == 0),
            "progress": f"{parsed}/3",
        },
        {
            "name": "AK first bullet moving < 60",
            "status": _status(ak_f is not None and ak_f < 60, ak_f is not None, ak_f is None),
            "progress": f"{ak_f}%" if ak_f is not None else "no data",
        },
        {
            "name": "M4 long spray < 40",
            "status": _status(m4_l is not None and m4_l < 40, m4_l is not None, m4_l is None),
            "progress": f"{m4_l}%" if m4_l is not None else "no data",
        },
        {
            "name": "Starter pistol first bullet < 65",
            "status": _status(sp is not None and sp < 65, sp is not None, sp is None),
            "progress": f"{sp}%" if sp is not None else "no data",
        },
        {
            "name": f"{weak or 'weak map'} dışı 1 map geliştirme",
            "status": "in progress" if weak else "no data",
            "progress": weak or "unavailable",
        },
        {
            "name": "Günde max 2 maç kuralı",
            "status": "in progress",
            "progress": "manual tracking",
        },
    ]

    return {
        "title": "Operation: Level 10 Push",
        "missions": [
            {
                "name": metric(m["name"], source=SOURCE_DERIVED),
                "status": metric(m["status"], source=SOURCE_DEMO if "demo" in m["name"].lower() else SOURCE_DERIVED),
                "progress": metric(m["progress"], source=SOURCE_DERIVED),
            }
            for m in missions
        ],
    }


def _status(completed: bool, in_progress: bool, no_data: bool) -> str:
    if no_data:
        return "no data"
    if completed:
        return "completed"
    if in_progress:
        return "in progress"
    return "failed"


def render_operation_markdown(section: dict[str, Any]) -> list[str]:
    lines = [
        f"## {section.get('title', 'Operation')}",
        "",
        "| Mission | Status | Progress |",
        "| --- | --- | --- |",
    ]
    for m in section.get("missions") or []:
        lines.append(
            f"| {fmt_simple(m.get('name'))} | {fmt_simple(m.get('status'))} | "
            f"{fmt_simple(m.get('progress'))} |"
        )
    lines.append("")
    return lines
