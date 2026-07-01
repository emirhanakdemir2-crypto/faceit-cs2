from __future__ import annotations

from typing import Any

from src.coach_ratings import (
    compute_aim_discipline,
    compute_coach_rating,
    compute_level10_gap,
    compute_mechanics_risk,
)
from src.suite_common import SOURCE_FACEIT, SOURCE_UNAVAILABLE, fmt_simple, metric


def analyze_dashboard(
    nickname: str,
    profile: dict[str, Any],
    summary: dict[str, Any],
    map_stats: dict[str, Any],
    mech: dict[str, Any],
) -> dict[str, Any]:
    coach = compute_coach_rating(summary, map_stats, mech)
    aim = compute_aim_discipline(mech)
    mech_risk = compute_mechanics_risk(mech)
    gap = compute_level10_gap(summary, map_stats, mech)

    return {
        "nickname": metric(nickname, source=SOURCE_FACEIT),
        "level": metric(profile.get("skill_level"), source=SOURCE_FACEIT),
        "elo": metric(profile.get("faceit_elo"), source=SOURCE_FACEIT),
        "highest_elo": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "analyzed_matches": metric(summary.get("total_matches"), source=SOURCE_FACEIT),
        "wins": metric(summary.get("wins"), source=SOURCE_FACEIT),
        "losses": metric(summary.get("losses"), source=SOURCE_FACEIT),
        "winrate": metric(summary.get("win_rate_pct"), source=SOURCE_FACEIT),
        "avg_kills": metric(summary.get("avg_kills"), source=SOURCE_FACEIT),
        "avg_deaths": metric(summary.get("avg_deaths"), source=SOURCE_FACEIT),
        "avg_assists": metric(summary.get("avg_assists"), source=SOURCE_FACEIT),
        "kd": metric(summary.get("avg_kd_ratio"), source=SOURCE_FACEIT),
        "kr": metric(summary.get("avg_kr_ratio"), source=SOURCE_FACEIT),
        "adr": metric(summary.get("avg_adr"), source=SOURCE_FACEIT),
        "hs_pct": metric(summary.get("avg_headshot_pct"), source=SOURCE_FACEIT),
        "entry_stats": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "clutch_stats": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "utility_stats": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "coach_rating": coach,
        "aim_discipline": aim,
        "mechanics_risk": mech_risk,
        "level10_gap_score": gap,
    }


def render_dashboard_markdown(section: dict[str, Any]) -> list[str]:
    lines = [
        "## Dashboard",
        "",
        f"- Nickname: {fmt_simple(section.get('nickname'))}",
        f"- FACEIT Level: {fmt_simple(section.get('level'))}",
        f"- ELO: {fmt_simple(section.get('elo'))}",
        f"- Highest ELO: {fmt_simple(section.get('highest_elo'))}",
        f"- Analyzed matches: {fmt_simple(section.get('analyzed_matches'))}",
        f"- W/L: {fmt_simple(section.get('wins'))}/{fmt_simple(section.get('losses'))}",
        f"- Winrate: {fmt_simple(section.get('winrate'))}%",
        f"- Avg K/D/A: {fmt_simple(section.get('avg_kills'))}/"
        f"{fmt_simple(section.get('avg_deaths'))}/{fmt_simple(section.get('avg_assists'))}",
        f"- K/D: {fmt_simple(section.get('kd'))} | K/R: {fmt_simple(section.get('kr'))}",
        f"- ADR: {fmt_simple(section.get('adr'))} | HS%: {fmt_simple(section.get('hs_pct'))}",
        f"- Entry stats: {fmt_simple(section.get('entry_stats'))}",
        f"- Clutch stats: {fmt_simple(section.get('clutch_stats'))}",
        f"- Utility stats: {fmt_simple(section.get('utility_stats'))}",
        f"- **Coach Rating:** {fmt_simple(section.get('coach_rating'))}",
        f"- **Aim Discipline:** {fmt_simple(section.get('aim_discipline'))}",
        f"- **Mechanics Risk:** {fmt_simple(section.get('mechanics_risk'))}",
        f"- **Level 10 Gap Score:** {fmt_simple(section.get('level10_gap_score'))}",
        "",
    ]
    return lines
