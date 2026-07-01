from __future__ import annotations

from typing import Any

from src.coach_ratings import compute_aim_discipline
from src.suite_common import SOURCE_DEMO, SOURCE_UNAVAILABLE, as_float, fmt_simple, metric


def analyze_aim(mech: dict[str, Any]) -> dict[str, Any]:
    ak = mech.get("ak_metrics") or {}
    m4 = mech.get("m4_metrics") or {}
    aim_score = compute_aim_discipline(mech)

    verdicts: list[str] = []
    rf = as_float(mech.get("rifle_first_bullet_moving_pct"))
    rl = as_float(mech.get("rifle_long_spray_pct"))
    sp = as_float(mech.get("starter_pistol_first_bullet_moving_pct"))
    ak_f = as_float(ak.get("first_bullet_moving_pct"))
    m4_l = as_float(m4.get("long_spray_pct"))

    if rf is not None and rf > 55:
        verdicts.append("Counter-strafe timing problem")
    if rl is not None and rl > 40:
        verdicts.append("Spray reset problem")
    if sp is not None and sp > 55:
        verdicts.append("Pistol ADAD early click")
    if ak_f is not None and rf is not None and ak_f > rf + 10:
        verdicts.append("Aim potential good, fire discipline weak")
    if not verdicts:
        verdicts.append("No major aim discipline signal")

    src = SOURCE_DEMO if mech.get("rifle_reliable") else SOURCE_UNAVAILABLE

    def m(key: str, sub: dict | None = None):
        d = sub or mech
        val = d.get(key)
        if val is None or val == "":
            return metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none")
        return metric(val, source=src, confidence="medium" if mech.get("rifle_reliable") else "low")

    return {
        "aim_discipline_score": aim_score,
        "rifle_first_bullet_moving_pct": m("rifle_first_bullet_moving_pct"),
        "rifle_shots_while_moving_pct": m("rifle_shots_while_moving_pct"),
        "rifle_average_speed_at_shot": m("rifle_average_speed_at_shot"),
        "rifle_median_speed_at_shot": m("rifle_median_speed_at_shot"),
        "rifle_spray_length_average": m("rifle_spray_length_average"),
        "rifle_long_spray_pct": m("rifle_long_spray_pct"),
        "ak_first_bullet": m("first_bullet_moving_pct", ak),
        "ak_shots_moving": m("shots_while_moving_pct", ak),
        "ak_spray_avg": m("spray_length_average", ak),
        "ak_long_spray": m("long_spray_pct", ak),
        "m4_first_bullet": m("first_bullet_moving_pct", m4),
        "m4_shots_moving": m("shots_while_moving_pct", m4),
        "m4_spray_avg": m("spray_length_average", m4),
        "m4_long_spray": m("long_spray_pct", m4),
        "pistol_first_bullet": m("pistol_first_bullet_moving_pct"),
        "starter_pistol_first": m("starter_pistol_first_bullet_moving_pct"),
        "force_pistol_moving": m("force_pistol_shots_while_moving_pct"),
        "smg_long_spray": m("smg_long_spray_pct"),
        "crosshair_placement": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "verdicts": verdicts,
    }


def render_aim_markdown(section: dict[str, Any]) -> list[str]:
    lines = [
        "## Aim",
        "",
        f"- Aim Discipline Score: {fmt_simple(section.get('aim_discipline_score'))}",
        f"- rifle_first_bullet_moving_pct: {fmt_simple(section.get('rifle_first_bullet_moving_pct'))}",
        f"- rifle_shots_while_moving_pct: {fmt_simple(section.get('rifle_shots_while_moving_pct'))}",
        f"- rifle_average_speed_at_shot: {fmt_simple(section.get('rifle_average_speed_at_shot'))}",
        f"- rifle_median_speed_at_shot: {fmt_simple(section.get('rifle_median_speed_at_shot'))}",
        f"- rifle_spray_length_average: {fmt_simple(section.get('rifle_spray_length_average'))}",
        f"- rifle_long_spray_pct: {fmt_simple(section.get('rifle_long_spray_pct'))}",
        f"- AK first bullet / moving / spray / long: "
        f"{fmt_simple(section.get('ak_first_bullet'))} / {fmt_simple(section.get('ak_shots_moving'))} / "
        f"{fmt_simple(section.get('ak_spray_avg'))} / {fmt_simple(section.get('ak_long_spray'))}",
        f"- M4 first bullet / moving / spray / long: "
        f"{fmt_simple(section.get('m4_first_bullet'))} / {fmt_simple(section.get('m4_shots_moving'))} / "
        f"{fmt_simple(section.get('m4_spray_avg'))} / {fmt_simple(section.get('m4_long_spray'))}",
        f"- pistol / starter / force moving: "
        f"{fmt_simple(section.get('pistol_first_bullet'))} / {fmt_simple(section.get('starter_pistol_first'))} / "
        f"{fmt_simple(section.get('force_pistol_moving'))}",
        f"- SMG long spray: {fmt_simple(section.get('smg_long_spray'))}",
        f"- Crosshair placement: {fmt_simple(section.get('crosshair_placement'))}",
        "",
        "**Aim verdict:**",
        "",
    ]
    for v in section.get("verdicts") or []:
        lines.append(f"- {v}")
    lines.append("")
    return lines
