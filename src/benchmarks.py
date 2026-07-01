from __future__ import annotations

from typing import Any

from src import suite_config as cfg
from src.suite_common import SOURCE_DERIVED, as_float, fmt_simple, metric


def _verdict(current: float | None, target: float, *, higher_is_better: bool = True) -> str:
    if current is None:
        return "no data"
    if higher_is_better:
        if current >= target:
            return "above target"
        if current >= target * 0.92:
            return "near target"
        return "below target"
    if current <= target:
        return "above target"
    if current <= target * 1.15:
        return "near target"
    return "below target"


def analyze_benchmarks(
    profile: dict[str, Any],
    summary: dict[str, Any],
    map_stats: dict[str, Any],
    mech: dict[str, Any],
    memory: dict[str, Any] | None,
) -> dict[str, Any]:
    level = profile.get("skill_level")
    rows: list[dict[str, Any]] = []

    def row(name: str, current: Any, target: str, verdict: str):
        rows.append({
            "metric": name,
            "current": metric(current, source=SOURCE_DERIVED),
            "level10_target": metric(target, source=SOURCE_DERIVED),
            "verdict": metric(verdict, source=SOURCE_DERIVED),
        })

    kd = as_float(summary.get("avg_kd_ratio"))
    adr = as_float(summary.get("avg_adr"))
    wr = as_float(summary.get("win_rate_pct"))
    hs = as_float(summary.get("avg_headshot_pct"))
    rf = as_float(mech.get("rifle_first_bullet_moving_pct"))
    rl = as_float(mech.get("rifle_long_spray_pct"))
    sp = as_float(mech.get("starter_pistol_first_bullet_moving_pct"))
    usable_maps = sum(
        1 for r in (map_stats.get("maps") or [])
        if (r.get("played") or 0) >= cfg.MAP_USABLE_MIN
    )

    row("K/D", kd, f">= {cfg.TARGET_KD}", _verdict(kd, cfg.TARGET_KD))
    row("ADR", adr, f">= {cfg.TARGET_ADR}", _verdict(adr, cfg.TARGET_ADR))
    row("HS%", hs, f">= {cfg.TARGET_HS_PCT}", _verdict(hs, cfg.TARGET_HS_PCT))
    row("Winrate", wr, f">= {cfg.TARGET_WINRATE}%", _verdict(wr, cfg.TARGET_WINRATE))
    row("Rifle first bullet moving", rf, f"< {cfg.TARGET_RIFLE_FIRST_BULLET_MOVING}%",
        _verdict(rf, cfg.TARGET_RIFLE_FIRST_BULLET_MOVING, higher_is_better=False))
    row("Rifle long spray", rl, f"< {cfg.TARGET_RIFLE_LONG_SPRAY}%",
        _verdict(rl, cfg.TARGET_RIFLE_LONG_SPRAY, higher_is_better=False))
    row("Starter pistol first bullet", sp, f"< {cfg.TARGET_STARTER_PISTOL_FIRST_BULLET}%",
        _verdict(sp, cfg.TARGET_STARTER_PISTOL_FIRST_BULLET, higher_is_better=False))
    row("Map pool (usable maps)", usable_maps, ">= 2",
        "above target" if usable_maps >= 2 else "below target")

    session_disc = "near target"
    if memory and "düşük" in str(memory.get("unchanged_problems", "")):
        session_disc = "below target"
    row("Session discipline", "estimated", "stable sessions", session_disc)

    prev_kd = None
    if memory and memory.get("previous_analysis_date"):
        prev_kd = "own previous best: unavailable"

    return {
        "current_level": metric(level, source=SOURCE_DERIVED),
        "target_level": metric(cfg.LEVEL_10_TARGET_LEVEL, source=SOURCE_DERIVED),
        "rows": rows,
        "previous_best_note": metric(prev_kd or "unavailable", source=SOURCE_DERIVED, confidence="low"),
    }


def render_benchmarks_markdown(section: dict[str, Any]) -> list[str]:
    lines = [
        "## Benchmarks",
        "",
        f"- Current level: {fmt_simple(section.get('current_level'))}",
        f"- Level 10 target thresholds",
        f"- Own previous best: {fmt_simple(section.get('previous_best_note'))}",
        "",
        "| Metric | Current | L10 Target | Verdict |",
        "| --- | --- | --- | --- |",
    ]
    for r in section.get("rows") or []:
        lines.append(
            f"| {r.get('metric')} | {fmt_simple(r.get('current'))} | "
            f"{fmt_simple(r.get('level10_target'))} | {fmt_simple(r.get('verdict'))} |"
        )
    lines.append("")
    return lines
