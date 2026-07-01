from __future__ import annotations

from typing import Any

from src import suite_config as cfg
from src.suite_common import SOURCE_DERIVED, SOURCE_FACEIT, fmt_simple, metric


def _map_confidence(played: int) -> str:
    if played <= cfg.MAP_VERY_LOW_MAX:
        return "very low sample"
    if cfg.MAP_LOW_MIN <= played <= cfg.MAP_LOW_MAX:
        return "low sample"
    if played >= cfg.MAP_USABLE_MIN:
        return "usable"
    return "low sample"


def analyze_maps(
    map_stats: dict[str, Any],
    matches: list[dict[str, Any]],
    mechanics_lab: dict[str, Any] | None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in map_stats.get("maps") or []:
        played = row.get("played") or 0
        map_name = row.get("map")
        map_kds = [
            m.get("kd_ratio") for m in matches
            if m.get("map") == map_name and m.get("stats_available")
        ]
        map_adrs = [
            m.get("adr") for m in matches
            if m.get("map") == map_name and m.get("stats_available")
        ]
        avg_kd = None
        avg_adr = None
        try:
            nums = [float(k) for k in map_kds if k not in (None, "veri eksik")]
            if nums:
                avg_kd = round(sum(nums) / len(nums), 2)
            nums = [float(a) for a in map_adrs if a not in (None, "veri eksik")]
            if nums:
                avg_adr = round(sum(nums) / len(nums), 1)
        except (TypeError, ValueError):
            pass

        rows.append({
            "map": metric(map_name, source=SOURCE_FACEIT),
            "matches": metric(played, source=SOURCE_FACEIT),
            "winrate": metric(row.get("win_rate_pct"), source=SOURCE_FACEIT),
            "kd": metric(avg_kd, source=SOURCE_DERIVED, confidence=_map_confidence(played)),
            "adr": metric(avg_adr, source=SOURCE_DERIVED, confidence=_map_confidence(played)),
            "hs_pct": metric("unavailable", source="Unavailable", confidence="none"),
            "confidence": metric(_map_confidence(played), source=SOURCE_DERIVED),
            "side_stats": metric("unavailable", source="Unavailable", confidence="none"),
            "mechanics": metric("unavailable", source="Unavailable", confidence="none"),
        })

    best = map_stats.get("best_map")
    worst = map_stats.get("worst_map")
    low = map_stats.get("low_sample_maps") or []
    usable = [r for r in rows if fmt_simple(r.get("confidence")) == "usable"]

    main_map = best
    dev_maps = [fmt_simple(r.get("map")) for r in usable if fmt_simple(r.get("map")) != best][:2]
    avoid = [fmt_simple(r.get("map")) for r in usable
             if r.get("map") and fmt_simple(r.get("winrate")) not in ("unavailable",)
             and float(fmt_simple(r.get("winrate")) or 0) < 40] if usable else []
    low_names = [f"{r.get('map')} ({r.get('played')} maç)" for r in low]

    verdict = {
        "main_map": metric(main_map, source=SOURCE_FACEIT),
        "development_maps": metric(dev_maps or "unavailable", source=SOURCE_DERIVED),
        "avoid_maps": metric(avoid or "none flagged", source=SOURCE_DERIVED),
        "low_sample_maps": metric(low_names or "none", source=SOURCE_FACEIT),
        "worst_usable": metric(worst, source=SOURCE_FACEIT),
    }

    return {"rows": rows, "verdict": verdict}


def render_maps_markdown(section: dict[str, Any]) -> list[str]:
    v = section.get("verdict") or {}
    lines = [
        "## Maps",
        "",
        f"- Main map: {fmt_simple(v.get('main_map'))}",
        f"- Development maps: {fmt_simple(v.get('development_maps'))}",
        f"- Avoid/ban: {fmt_simple(v.get('avoid_maps'))}",
        f"- Low sample: {fmt_simple(v.get('low_sample_maps'))}",
        f"- Worst (min 10 maç): {fmt_simple(v.get('worst_usable'))}",
        "",
        "| Map | Matches | WR% | K/D | ADR | Confidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in section.get("rows") or []:
        lines.append(
            f"| {fmt_simple(row.get('map'))} | {fmt_simple(row.get('matches'))} | "
            f"{fmt_simple(row.get('winrate'))} | {fmt_simple(row.get('kd'))} | "
            f"{fmt_simple(row.get('adr'))} | {fmt_simple(row.get('confidence'))} |"
        )
    lines.append("")
    return lines
