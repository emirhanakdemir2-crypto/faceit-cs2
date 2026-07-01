from __future__ import annotations

from typing import Any

from src.coach_ratings import compute_aim_discipline, compute_mechanics_risk
from src.metrics import compute_recent_form
from src.suite_common import SOURCE_DERIVED, SOURCE_FACEIT, fmt_simple, metric, metric_val


def analyze_home(
    profile: dict[str, Any],
    summary: dict[str, Any],
    form5: dict[str, Any],
    matches: list[dict[str, Any]],
    mech: dict[str, Any],
    focus_areas: list[dict[str, Any]],
    session_coach: dict[str, Any] | None,
) -> dict[str, Any]:
    form10 = compute_recent_form({"matches": matches}, count=10)
    mech_risk = compute_mechanics_risk(mech)
    aim = compute_aim_discipline(mech)

    risk_band = "medium"
    risk_val = metric_val(mech_risk)
    if isinstance(risk_val, dict):
        risk_band = risk_val.get("band", "medium")

    queue = "2–3 maç"
    if session_coach:
        queue = session_coach.get("focus_risk", {}).get("queue_decision", queue)
    elif risk_band == "high":
        queue = "Maksimum 1–2 maç"
    elif risk_band == "low":
        queue = "2–3 maç güvenli"

    main_focus = "Genel tutarlılık"
    if focus_areas:
        main_focus = focus_areas[0].get("title", main_focus)

    faceit_risk = "orta"
    if risk_band == "high":
        faceit_risk = "yüksek"
    elif risk_band == "low":
        faceit_risk = "düşük"

    work = []
    for fa in focus_areas[:3]:
        drill = fa.get("drill")
        if drill:
            work.append(drill)

    return {
        "level": metric(profile.get("skill_level"), source=SOURCE_FACEIT),
        "elo": metric(profile.get("faceit_elo"), source=SOURCE_FACEIT),
        "matches_90d": metric(summary.get("total_matches"), source=SOURCE_FACEIT),
        "winrate": metric(summary.get("win_rate_pct"), source=SOURCE_FACEIT),
        "kd": metric(summary.get("avg_kd_ratio"), source=SOURCE_FACEIT),
        "adr": metric(summary.get("avg_adr"), source=SOURCE_FACEIT),
        "hs_pct": metric(summary.get("avg_headshot_pct"), source=SOURCE_FACEIT),
        "form_5": metric(form5.get("record"), source=SOURCE_FACEIT),
        "form_10": metric(form10.get("record"), source=SOURCE_FACEIT),
        "mechanics_warning": mech_risk,
        "aim_discipline": aim,
        "today_work": metric(work or ["5 dk warmup + 1 demo review"], source=SOURCE_DERIVED),
        "queue_decision": metric(queue, source=SOURCE_DERIVED),
        "faceit_risk": metric(faceit_risk, source=SOURCE_DERIVED),
        "main_focus": metric(main_focus, source=SOURCE_DERIVED),
        "commentary": [
            f"Bugün FACEIT için risk {faceit_risk}.",
            f"Ana çalışma: {main_focus}.",
            f"Önerilen maç sayısı: {queue}.",
        ],
    }


def render_home_markdown(section: dict[str, Any]) -> list[str]:
    lines = [
        "## Home Summary",
        "",
        f"- Level: {fmt_simple(section.get('level'))}",
        f"- ELO: {fmt_simple(section.get('elo'))}",
        f"- Son 90 gün maç: {fmt_simple(section.get('matches_90d'))}",
        f"- Winrate: {fmt_simple(section.get('winrate'))}%",
        f"- K/D: {fmt_simple(section.get('kd'))}",
        f"- ADR: {fmt_simple(section.get('adr'))}",
        f"- HS%: {fmt_simple(section.get('hs_pct'))}",
        f"- Son 5 maç: {fmt_simple(section.get('form_5'))}",
        f"- Son 10 maç: {fmt_simple(section.get('form_10'))}",
        f"- Mechanics warning: {fmt_simple(section.get('mechanics_warning'))}",
        f"- Bugünkü çalışma: {fmt_simple(section.get('today_work'))}",
        f"- Maç kararı: {fmt_simple(section.get('queue_decision'))}",
        "",
        "**Kısa yorum:**",
        "",
    ]
    for note in section.get("commentary") or []:
        lines.append(f"- {note}")
    lines.append("")
    return lines
