from __future__ import annotations

from pathlib import Path
from typing import Any

from src.suite_common import SOURCE_DEMO, SOURCE_UNAVAILABLE, fmt_simple, metric


UTILITY_EVENTS = (
    "flashbang_detonate",
    "player_blind",
    "hegrenade_detonate",
    "inferno_startburn",
    "inferno_expire",
    "smokegrenade_detonate",
    "smokegrenade_expired",
    "molotov_detonate",
)


def _try_parse_utility(demo_paths: list[str]) -> dict[str, Any] | None:
    try:
        from demoparser2 import DemoParser
    except ImportError:
        return None

    totals: dict[str, int] = {}
    blind_rows = 0
    for path_str in demo_paths[:3]:
        path = Path(path_str)
        if not path.exists():
            continue
        try:
            parser = DemoParser(str(path))
            events = parser.list_game_events()
            for ev_name in UTILITY_EVENTS:
                if ev_name not in events:
                    continue
                df = parser.parse_event(ev_name)
                count = len(df) if hasattr(df, "__len__") else 0
                totals[ev_name] = totals.get(ev_name, 0) + count
                if ev_name == "player_blind":
                    blind_rows += count
        except Exception:
            continue

    if not totals:
        return None
    return {"event_counts": totals, "blind_events": blind_rows}


def analyze_utility(
    mechanics_lab: dict[str, Any] | None,
    demo_folder: str | Path | None = None,
) -> dict[str, Any]:
    demo_paths: list[str] = []
    if mechanics_lab:
        for d in mechanics_lab.get("demos") or []:
            if d.get("status") == "ok" and d.get("demo_path"):
                demo_paths.append(d["demo_path"])
            elif d.get("status") == "ok":
                fname = d.get("demo_file")
                if fname and demo_folder:
                    demo_paths.append(str(Path(demo_folder) / fname))

    parsed = _try_parse_utility(demo_paths) if demo_paths else None

    if not parsed:
        return {
            "available": False,
            "utility_impact": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "flashes_thrown": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "enemies_flashed": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "teammates_flashed": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "self_flash_count": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "avg_enemy_flash_duration": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "flash_assists": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "he_damage": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "molotov_damage": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "utility_damage_per_round": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "smokes_thrown": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "useful_smoke_estimate": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "team_flash_rate": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "note": "Utility event verisi yetersiz; fake yorum yapılmadı.",
        }

    ec = parsed["event_counts"]
    flashes = ec.get("flashbang_detonate", 0)
    smokes = ec.get("smokegrenade_detonate", 0) + ec.get("smokegrenade_expired", 0)
    he = ec.get("hegrenade_detonate", 0)
    molly = ec.get("molotov_detonate", 0) + ec.get("inferno_startburn", 0)

    impact = None  # player-specific impact requires filtered events; not estimated

    return {
        "available": True,
        "utility_impact": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "flashes_thrown": metric(flashes, source=SOURCE_DEMO, confidence="low"),
        "enemies_flashed": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "teammates_flashed": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "self_flash_count": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "avg_enemy_flash_duration": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "flash_assists": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "he_damage": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "molotov_damage": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "utility_damage_per_round": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "smokes_thrown": metric(smokes, source=SOURCE_DEMO, confidence="low"),
        "useful_smoke_estimate": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "team_flash_rate": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "note": (
            "Ham event sayıları (demo geneli, oyuncu filtresi yok); "
            "Utility Impact ve damage metrikleri unavailable."
        ),
    }


def render_utility_markdown(section: dict[str, Any]) -> list[str]:
    lines = [
        "## Utility",
        "",
        f"- Utility Impact: {fmt_simple(section.get('utility_impact'))}",
        f"- Flashes thrown: {fmt_simple(section.get('flashes_thrown'))}",
        f"- Enemies flashed: {fmt_simple(section.get('enemies_flashed'))}",
        f"- Teammates flashed: {fmt_simple(section.get('teammates_flashed'))}",
        f"- Self flash: {fmt_simple(section.get('self_flash_count'))}",
        f"- Avg enemy flash duration: {fmt_simple(section.get('avg_enemy_flash_duration'))}",
        f"- Flash assists: {fmt_simple(section.get('flash_assists'))}",
        f"- HE damage: {fmt_simple(section.get('he_damage'))}",
        f"- Molotov damage: {fmt_simple(section.get('molotov_damage'))}",
        f"- Utility dmg/round: {fmt_simple(section.get('utility_damage_per_round'))}",
        f"- Smokes thrown: {fmt_simple(section.get('smokes_thrown'))}",
        f"- Useful smoke estimate: {fmt_simple(section.get('useful_smoke_estimate'))}",
        f"- Team flash rate: {fmt_simple(section.get('team_flash_rate'))}",
        "",
        f"_{section.get('note', '')}_",
        "",
    ]
    return lines
