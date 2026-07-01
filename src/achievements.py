from __future__ import annotations

from typing import Any

from src import suite_config as cfg
from src.suite_common import SOURCE_DERIVED, SOURCE_FACEIT, as_float, fmt_simple, metric


def analyze_achievements(
    summary: dict[str, Any],
    map_stats: dict[str, Any],
    matches: list[dict[str, Any]],
    mech: dict[str, Any],
    memory: dict[str, Any] | None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    best_adr = as_float(summary.get("avg_adr"))
    best_kd = as_float(summary.get("best_kd_value"))
    if best_adr and best_adr >= cfg.TARGET_ADR:
        items.append({"name": "ADR machine", "detail": f"Avg ADR {best_adr}", "source": SOURCE_FACEIT})
    if best_kd and best_kd >= 1.5:
        items.append({"name": "Frag peak", "detail": f"Best K/D {best_kd}", "source": SOURCE_FACEIT})

    best_map = map_stats.get("best_map")
    for row in map_stats.get("maps") or []:
        if row.get("map") == best_map and (row.get("played") or 0) >= cfg.MAP_USABLE_MIN:
            wr = as_float(row.get("win_rate_pct"))
            if wr and wr >= 60:
                items.append({
                    "name": f"{best_map} specialist",
                    "detail": f"WR {wr}%",
                    "source": SOURCE_FACEIT,
                })

    ak_f = as_float((mech.get("ak_metrics") or {}).get("first_bullet_moving_pct"))
    if ak_f is not None and ak_f < 60:
        items.append({"name": "AK discipline target", "detail": f"AK first bullet {ak_f}% < 60", "source": SOURCE_DERIVED})

    sp = as_float(mech.get("starter_pistol_first_bullet_moving_pct"))
    if sp is not None and sp < 65:
        items.append({"name": "Pistol stability progress", "detail": f"Starter {sp}%", "source": SOURCE_DERIVED})

    # recent 2-win session
    wins_run = 0
    for m in matches[:10]:
        if m.get("won") is True:
            wins_run += 1
        else:
            break
    if wins_run >= 2:
        items.append({"name": "2-win session", "detail": f"{wins_run}W streak start", "source": SOURCE_FACEIT})

    if memory and memory.get("improved_areas"):
        for imp in memory.get("improved_areas") or []:
            if "K/D" in str(imp) or "ADR" in str(imp):
                items.append({"name": "Progress milestone", "detail": str(imp), "source": SOURCE_DERIVED})
                break

    if not items:
        items.append({"name": "Baseline set", "detail": "İlk analiz milestone", "source": SOURCE_DERIVED})

    return {"items": [metric(i["name"] + ": " + i["detail"], source=i["source"]) for i in items]}


def render_achievements_markdown(section: dict[str, Any]) -> list[str]:
    lines = ["## Achievements", ""]
    for item in section.get("items") or []:
        lines.append(f"- {fmt_simple(item)}")
    lines.append("")
    return lines
