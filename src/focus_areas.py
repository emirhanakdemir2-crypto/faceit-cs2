from __future__ import annotations

from typing import Any

from src import suite_config as cfg
from src.metrics import compute_recent_form
from src.suite_common import SOURCE_DERIVED, SOURCE_DEMO, SOURCE_FACEIT, as_float, fmt_simple, metric


def analyze_focus_areas(
    summary: dict[str, Any],
    map_stats: dict[str, Any],
    mech: dict[str, Any],
    matches: list[dict[str, Any]],
    impact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    areas: list[dict[str, Any]] = []
    ak = mech.get("ak_metrics") or {}
    m4 = mech.get("m4_metrics") or {}

    def add(title: str, metric_name: str, value: Any, target: str, drill: str, why: str):
        areas.append({
            "title": title,
            "metric": metric(value, source=SOURCE_DEMO if mech.get("rifle_reliable") else SOURCE_FACEIT),
            "metric_name": metric_name,
            "target": target,
            "drill": drill,
            "why": why,
        })

    rf = as_float(mech.get("rifle_first_bullet_moving_pct"))
    if rf is not None and rf > cfg.FOCUS_RIFLE_FIRST_BULLET:
        add("Rifle first bullet stability", "rifle_first_bullet_moving_pct", f"{rf}%",
            f"<{cfg.TARGET_RIFLE_FIRST_BULLET_MOVING}%",
            "5 dk counter-strafe + 1 tap", "İlk mermi hareket halinde isabet düşer.")

    ak_f = as_float(ak.get("first_bullet_moving_pct"))
    if ak_f is not None and ak_f > cfg.FOCUS_AK_FIRST_BULLET:
        add("AK counter-strafe timing", "AK first bullet moving", f"{ak_f}%",
            f"<{cfg.TARGET_AK_FIRST_BULLET}%",
            "5 dk A-D stop one tap", "AK peek'lerinde reset gecikmesi.")

    m4_l = as_float(m4.get("long_spray_pct"))
    if m4_l is not None and m4_l > cfg.FOCUS_M4_LONG_SPRAY:
        add("M4 spray reset", "M4 long spray", f"{m4_l}%",
            f"<{cfg.TARGET_M4_LONG_SPRAY}%",
            "5 dk 5-bullet burst + reset", "M4 spray kontrolü zayıf.")

    sp = as_float(mech.get("starter_pistol_first_bullet_moving_pct"))
    if sp is not None and sp > cfg.FOCUS_STARTER_PISTOL_FIRST:
        add("Pistol round stability", "starter pistol first bullet", f"{sp}%",
            f"<{cfg.TARGET_STARTER_PISTOL_FIRST_BULLET}%",
            "5 dk USP/Glock stop-shot", "Pistol round ekonomisi etkilenir.")

    worst = map_stats.get("worst_map")
    worst_row = next(
        (r for r in (map_stats.get("maps") or [])
         if r.get("map") == worst and (r.get("played") or 0) >= cfg.MAP_USABLE_MIN),
        None,
    )
    if worst_row and as_float(worst_row.get("win_rate_pct")) is not None:
        wr = float(worst_row["win_rate_pct"])
        if wr < cfg.FOCUS_WEAK_MAP_WR:
            add("Map weakness", f"{worst} WR", f"{wr}%", f">{cfg.FOCUS_WEAK_MAP_WR}%",
                f"{worst} demo review", "Harita havuzunda zayıf link.")

    form10 = compute_recent_form({"matches": matches}, count=10)
    rec = form10.get("record", "")
    if isinstance(rec, str) and rec.count("L") >= 6:
        add("Session discipline", "Son 10 form", rec, "Daha dengeli session",
            "Günde max 2 maç kuralı", "Tilt/fatigue riski.")

    kd = as_float(summary.get("avg_kd_ratio"))
    wr_all = as_float(summary.get("win_rate_pct"))
    if kd is not None and kd >= 1.1 and wr_all is not None and wr_all < 48:
        add("Impact conversion", "K/D vs WR", f"K/D {kd}, WR {wr_all}%",
            "WR > 50%", "Round win trade review", "İyi frag ama round kazanma düşük.")

    imp = impact or {}
    if imp.get("reliable"):
        untraded = as_float(imp.get("untraded_death_pct"))
        if untraded is not None and untraded > cfg.UNTRADED_DEATH_OKAY:
            add(
                "Death quality — untraded deaths",
                "untraded_death_pct",
                f"{untraded}%",
                f"< {cfg.TARGET_UNTRADED_DEATH_PCT}%",
                "Trade mesafesi + 2nd entry drill",
                "Yalnız ölümler fazla; takım trade'i kaçırıyor.",
            )
        early = as_float(imp.get("early_death_pct"))
        if early is not None and early > cfg.EARLY_DEATH_OKAY:
            add(
                "Death quality — early deaths",
                "early_death_pct",
                f"{early}%",
                f"< {cfg.TARGET_EARLY_DEATH_PCT}%",
                "Default timing + info review",
                "Round başında erken ölüm oranı yüksek.",
            )
        surv = as_float(imp.get("post_kill_survival_rate_5s"))
        if surv is not None and surv < cfg.POST_KILL_SURVIVAL_OKAY:
            add(
                "Death quality — post-kill reset",
                "post_kill_survival_rate_5s",
                f"{surv}%",
                f"> {cfg.TARGET_POST_KILL_SURVIVAL_5S}%",
                "Kill sonrası pozisyon + cover drill",
                "Kill sonrası reset zayıf.",
            )

    return {"areas": areas[:5]}


def render_focus_areas_markdown(section: dict[str, Any]) -> list[str]:
    lines = ["## Focus Areas", ""]
    for i, area in enumerate(section.get("areas") or [], 1):
        lines.extend([
            f"### {i}. {area.get('title')}",
            f"- Metric: {area.get('metric_name')} = {fmt_simple(area.get('metric'))}",
            f"- Target: {area.get('target')}",
            f"- Why: {area.get('why')}",
            f"- Drill: {area.get('drill')}",
            "",
        ])
    if not section.get("areas"):
        lines.append("_Belirgin focus area tespit edilmedi._")
        lines.append("")
    return lines
