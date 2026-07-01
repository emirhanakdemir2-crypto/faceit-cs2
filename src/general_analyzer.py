from __future__ import annotations

from typing import Any

from src.metrics import compute_recent_form
from src.suite_common import SOURCE_DERIVED, SOURCE_FACEIT, SOURCE_UNAVAILABLE, as_float, fmt_simple, metric


def _consistency_score(matches: list[dict[str, Any]]) -> dict[str, Any]:
    kds = [as_float(m.get("kd_ratio")) for m in matches if m.get("stats_available")]
    kds = [k for k in kds if k is not None]
    if len(kds) < 5:
        return metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none")
    mean = sum(kds) / len(kds)
    var = sum((k - mean) ** 2 for k in kds) / len(kds)
    std = var ** 0.5
    score = max(0, min(100, int(100 - std * 40)))
    return metric(score, source=SOURCE_DERIVED, confidence="medium")


def _role_guess(summary: dict[str, Any], mech: dict[str, Any]) -> dict[str, Any]:
    kd = as_float(summary.get("avg_kd_ratio"))
    adr = as_float(summary.get("avg_adr"))
    notes = []
    if kd is not None and kd >= 1.1 and adr is not None and adr >= 80:
        notes.append("2nd entry/trade rifler potansiyeli")
    else:
        notes.append("2nd entry/trade rifler (düşük güven)")
    notes.append("active CT rotator — opening/trade verisi yok, düşük güven")
    if kd is not None and kd < 0.95:
        notes.append("Hard entry'den kaçın; opening death verisi yok")
    notes.append("Full lurker — trade impact verisi yoksa önerilmez")
    return metric("; ".join(notes), source=SOURCE_DERIVED, confidence="low")


def analyze_general(
    profile: dict[str, Any],
    summary: dict[str, Any],
    form: dict[str, Any],
    matches: list[dict[str, Any]],
    period_insights: list[str] | None,
    mech: dict[str, Any],
) -> dict[str, Any]:
    form10 = compute_recent_form({"matches": matches}, count=10)
    trend = period_insights[0] if period_insights else "Trend verisi sınırlı."

    return {
        "profile": metric(profile.get("nickname"), source=SOURCE_FACEIT),
        "country": metric(profile.get("country"), source=SOURCE_FACEIT),
        "level": metric(profile.get("skill_level"), source=SOURCE_FACEIT),
        "elo": metric(profile.get("faceit_elo"), source=SOURCE_FACEIT),
        "overall_stats": metric(summary, source=SOURCE_FACEIT),
        "recent_form_5": metric(form.get("record"), source=SOURCE_FACEIT),
        "recent_form_10": metric(form10.get("record"), source=SOURCE_FACEIT),
        "long_term_trend": metric(trend, source=SOURCE_DERIVED, confidence="low"),
        "consistency_score": _consistency_score(matches),
        "best_role_guess": _role_guess(summary, mech),
    }


def render_general_markdown(section: dict[str, Any]) -> list[str]:
    s = section.get("overall_stats", {})
    val = s.get("value", s) if isinstance(s, dict) else s
    lines = [
        "## General",
        "",
        f"- Profile: {fmt_simple(section.get('profile'))}",
        f"- Country: {fmt_simple(section.get('country'))}",
        f"- Level / ELO: {fmt_simple(section.get('level'))} / {fmt_simple(section.get('elo'))}",
        f"- Analyzed matches: {val.get('total_matches') if isinstance(val, dict) else 'unavailable'}",
        f"- Winrate: {val.get('win_rate_pct') if isinstance(val, dict) else 'unavailable'}%",
        f"- K/D / ADR: {val.get('avg_kd_ratio') if isinstance(val, dict) else 'unavailable'} / "
        f"{val.get('avg_adr') if isinstance(val, dict) else 'unavailable'}",
        f"- Son 5 maç: {fmt_simple(section.get('recent_form_5'))}",
        f"- Son 10 maç: {fmt_simple(section.get('recent_form_10'))}",
        f"- Long-term trend: {fmt_simple(section.get('long_term_trend'))}",
        f"- Consistency score: {fmt_simple(section.get('consistency_score'))}",
        f"- Best role guess: {fmt_simple(section.get('best_role_guess'))}",
        "",
    ]
    return lines
