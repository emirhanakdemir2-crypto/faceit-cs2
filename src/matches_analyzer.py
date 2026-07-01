from __future__ import annotations

from datetime import datetime
from typing import Any

from src.coach_ratings import compute_aim_discipline, compute_coach_rating
from src.config import MISSING_DATA_LABEL
from src.suite_common import SOURCE_DERIVED, SOURCE_DEMO, SOURCE_FACEIT, SOURCE_UNAVAILABLE, as_float, fmt_simple, metric


def _match_verdict(m: dict[str, Any], mech_warning: bool) -> str:
    kd = as_float(m.get("kd_ratio"))
    adr = as_float(m.get("adr"))
    won = m.get("won")
    if mech_warning:
        return "mechanics problem"
    if won is True and kd is not None and kd >= 1.2:
        return "good impact"
    if won is False and adr is not None and adr >= 80:
        return "high damage loss"
    if won is False:
        return "bad loss"
    if not m.get("stats_available"):
        return "low sample"
    return "neutral"


def _demo_for_match(demos: list[dict[str, Any]], match: dict[str, Any]) -> dict[str, Any] | None:
    mid = match.get("match_id")
    for d in demos:
        if d.get("match_id") == mid:
            return d
    return None


def analyze_matches(
    matches: list[dict[str, Any]],
    mechanics_lab: dict[str, Any] | None,
    summary: dict[str, Any],
    map_stats: dict[str, Any],
    mech: dict[str, Any],
) -> dict[str, Any]:
    demos = (mechanics_lab or {}).get("demos") or []
    parsed_files = {d.get("demo_file") for d in demos if d.get("status") == "ok"}
    rows: list[dict[str, Any]] = []

    for m in matches[:50]:
        demo_parsed = False
        demo_file = None
        source = SOURCE_FACEIT
        demo_impact = None
        mid = m.get("match_id")
        for d in demos:
            if d.get("match_id") == mid and d.get("status") == "ok":
                demo_parsed = True
                demo_file = d.get("demo_file")
                demo_impact = d.get("impact")
                source = SOURCE_FACEIT
                break

        mech_warn = False
        if mech.get("rifle_reliable"):
            rf = as_float(mech.get("rifle_first_bullet_moving_pct"))
            if rf and rf > 60:
                mech_warn = True

        coach = compute_coach_rating(
            {
                "avg_kd_ratio": m.get("kd_ratio"),
                "avg_adr": m.get("adr"),
                "win_rate_pct": 100 if m.get("won") is True else (0 if m.get("won") is False else None),
            },
            map_stats,
            mech,
        )
        aim = compute_aim_discipline(mech)

        finished = m.get("finished_at") or ""
        date_str = finished[:10] if finished else MISSING_DATA_LABEL
        result = "W" if m.get("won") is True else ("L" if m.get("won") is False else "?")

        rows.append({
            "date": metric(date_str, source=SOURCE_FACEIT),
            "map": metric(m.get("map"), source=SOURCE_FACEIT),
            "result": metric(result, source=SOURCE_FACEIT),
            "score": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "kda": metric(
                f"{m.get('kills', '?')}-{m.get('assists', '?')}-{m.get('deaths', '?')}",
                source=SOURCE_FACEIT,
            ),
            "kd": metric(m.get("kd_ratio"), source=SOURCE_FACEIT),
            "adr": metric(m.get("adr"), source=SOURCE_FACEIT),
            "hs_pct": metric(m.get("headshot_pct"), source=SOURCE_FACEIT),
            "elo_change": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
            "demo_parsed": metric("yes" if demo_parsed else "no", source=SOURCE_DEMO if demo_parsed else SOURCE_FACEIT),
            "demo_file": metric(demo_file or "unavailable", source=SOURCE_DEMO if demo_file else SOURCE_UNAVAILABLE),
            "match_id": metric(m.get("match_id"), source=SOURCE_FACEIT),
            "coach_rating": coach,
            "aim_discipline": aim,
            "mechanics_warning": metric(mech_warn, source=SOURCE_DEMO if mech_warn else SOURCE_DERIVED),
            "impact_rating": metric(
                demo_impact.get("impact_rating_0_100")
                if demo_impact and demo_impact.get("reliable")
                else "unavailable",
                source=SOURCE_DEMO if demo_impact and demo_impact.get("reliable") else SOURCE_UNAVAILABLE,
            ),
            "source": metric(source, source=source),
            "verdict": metric(_match_verdict(m, mech_warn), source=SOURCE_DERIVED),
        })

    for d in demos:
        if d.get("status") != "ok":
            continue
        fname = d.get("demo_file")
        already = any(
            fmt_simple(r.get("demo_file")) == fname for r in rows
        )
        if already:
            continue
        imp = d.get("impact") or {}
        rows.append({
            "date": metric("unavailable", source=SOURCE_UNAVAILABLE),
            "map": metric("unavailable", source=SOURCE_UNAVAILABLE),
            "result": metric("—", source=SOURCE_DEMO),
            "score": metric("unavailable", source=SOURCE_UNAVAILABLE),
            "kda": metric(f"{d.get('kills', '?')}-{d.get('deaths', '?')}", source=SOURCE_DEMO),
            "kd": metric("unavailable", source=SOURCE_UNAVAILABLE),
            "adr": metric("unavailable", source=SOURCE_UNAVAILABLE),
            "hs_pct": metric("unavailable", source=SOURCE_UNAVAILABLE),
            "elo_change": metric("unavailable", source=SOURCE_UNAVAILABLE),
            "demo_parsed": metric("yes", source=SOURCE_DEMO),
            "demo_file": metric(d.get("demo_file"), source=SOURCE_DEMO),
            "match_id": metric("unavailable", source=SOURCE_UNAVAILABLE),
            "coach_rating": metric("unavailable", source=SOURCE_UNAVAILABLE),
            "aim_discipline": metric("unavailable", source=SOURCE_UNAVAILABLE),
            "mechanics_warning": metric(False, source=SOURCE_DEMO),
            "impact_rating": metric(
                imp.get("impact_rating_0_100") if imp.get("reliable") else "unavailable",
                source=SOURCE_DEMO if imp.get("reliable") else SOURCE_UNAVAILABLE,
            ),
            "source": metric(SOURCE_DEMO, source=SOURCE_DEMO),
            "verdict": metric("uploaded demo", source=SOURCE_DEMO),
        })

    return {"rows": rows, "parsed_demo_files": list(parsed_files)}


def render_matches_markdown(section: dict[str, Any]) -> list[str]:
    lines = [
        "## Matches",
        "",
        "| Date | Map | Result | K-A-D | K/D | ADR | HS% | Demo | Impact | Verdict | Source |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in section.get("rows") or []:
        from src.suite_common import fmt_simple
        demo = fmt_simple(row.get("demo_parsed"))
        lines.append(
            f"| {fmt_simple(row.get('date'))} | {fmt_simple(row.get('map'))} | "
            f"{fmt_simple(row.get('result'))} | {fmt_simple(row.get('kda'))} | "
            f"{fmt_simple(row.get('kd'))} | {fmt_simple(row.get('adr'))} | "
            f"{fmt_simple(row.get('hs_pct'))} | {demo} | {fmt_simple(row.get('impact_rating'))} | "
            f"{fmt_simple(row.get('verdict'))} | "
            f"{fmt_simple(row.get('source'))} |"
        )
    lines.append("")
    if section.get("parsed_demo_files"):
        lines.append(f"_Parsed demos (filename): {', '.join(section['parsed_demo_files'])}_")
        lines.append("")
    return lines
