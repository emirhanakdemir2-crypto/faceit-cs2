from __future__ import annotations

from typing import Any

from src import suite_config as cfg
from src.suite_common import SOURCE_DERIVED, SOURCE_DEMO, SOURCE_FACEIT, as_float, clamp_score, metric


def compute_coach_rating(
    summary: dict[str, Any],
    map_stats: dict[str, Any],
    mech: dict[str, Any],
) -> dict[str, Any]:
    """0–100 Coach Rating (kendi formülümüz, Leetify değil)."""
    kd = as_float(summary.get("avg_kd_ratio"))
    adr = as_float(summary.get("avg_adr"))
    wr = as_float(summary.get("win_rate_pct"))
    if kd is None and adr is None and wr is None:
        return metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none")

    kd_s = min(100, (kd or 0) / cfg.TARGET_KD * 70) if kd else 40
    adr_s = min(100, (adr or 0) / cfg.TARGET_ADR * 70) if adr else 40
    wr_s = min(100, (wr or 0) / max(cfg.TARGET_WINRATE, 1) * 70) if wr else 40

    rifle_first = as_float(mech.get("rifle_first_bullet_moving_pct"))
    rifle_long = as_float(mech.get("rifle_long_spray_pct"))
    mech_s = 70.0
    if rifle_first is not None:
        mech_s -= max(0, rifle_first - cfg.TARGET_RIFLE_FIRST_BULLET_MOVING) * 0.8
    if rifle_long is not None:
        mech_s -= max(0, rifle_long - cfg.TARGET_RIFLE_LONG_SPRAY) * 0.6
    mech_s = max(0, min(100, mech_s))

    usable = [
        r for r in (map_stats.get("maps") or [])
        if (r.get("played") or 0) >= cfg.MAP_USABLE_MIN
    ]
    map_s = min(100, len(usable) * 35) if usable else 30

    cons_s = 60.0
    if wr is not None and kd is not None:
        if wr >= 50 and kd >= 1.0:
            cons_s = 75
        elif wr < 45 or kd < 0.9:
            cons_s = 45

    w = cfg.COACH_RATING_WEIGHTS
    score = (
        kd_s * w["kd"] + adr_s * w["adr"] + wr_s * w["winrate"]
        + mech_s * w["mechanics"] + map_s * w["map_pool"] + cons_s * w["consistency"]
    ) / sum(w.values()) * (100 / 70)

    conf = "medium"
    if mech.get("rifle_reliable"):
        conf = "medium"
    elif not mech:
        conf = "low"

    return metric(clamp_score(score), source=SOURCE_DERIVED, confidence=conf)


def compute_aim_discipline(mech: dict[str, Any]) -> dict[str, Any]:
    """0–100 Aim Discipline — fire discipline odaklı."""
    if not mech.get("rifle_reliable") and not mech.get("rifle_total_shots"):
        return metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none")

    score = 100.0
    rifle_first = as_float(mech.get("rifle_first_bullet_moving_pct"))
    rifle_mov = as_float(mech.get("rifle_shots_while_moving_pct"))
    rifle_long = as_float(mech.get("rifle_long_spray_pct"))
    starter = as_float(mech.get("starter_pistol_first_bullet_moving_pct"))
    ak = mech.get("ak_metrics") or {}
    m4 = mech.get("m4_metrics") or {}
    ak_first = as_float(ak.get("first_bullet_moving_pct"))
    m4_long = as_float(m4.get("long_spray_pct"))

    if rifle_first is not None:
        score -= max(0, rifle_first - 30) * 0.7
    if rifle_mov is not None:
        score -= max(0, rifle_mov - 35) * 0.5
    if rifle_long is not None:
        score -= max(0, rifle_long - 25) * 0.6
    if starter is not None:
        score -= max(0, starter - 40) * 0.4
    if ak_first is not None:
        score -= max(0, ak_first - 35) * 0.5
    if m4_long is not None:
        score -= max(0, m4_long - 30) * 0.5

    src = SOURCE_DEMO if mech.get("rifle_reliable") else SOURCE_DERIVED
    return metric(clamp_score(score), source=src, confidence="medium")


def compute_mechanics_risk(mech: dict[str, Any]) -> dict[str, Any]:
    if not mech.get("rifle_reliable"):
        return metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none")

    risk = 0.0
    rifle_first = as_float(mech.get("rifle_first_bullet_moving_pct"))
    rifle_long = as_float(mech.get("rifle_long_spray_pct"))
    starter = as_float(mech.get("starter_pistol_first_bullet_moving_pct"))

    if rifle_first is not None:
        risk += max(0, rifle_first - 50) * 0.8
    if rifle_long is not None:
        risk += max(0, rifle_long - 35) * 0.7
    if starter is not None:
        risk += max(0, starter - 55) * 0.5

    band = "low"
    if risk >= 40:
        band = "high"
    elif risk >= 20:
        band = "medium"

    return metric(
        {"score": clamp_score(risk), "band": band},
        source=SOURCE_DEMO,
        confidence="medium",
    )


def compute_level10_gap(
    summary: dict[str, Any],
    map_stats: dict[str, Any],
    mech: dict[str, Any],
) -> dict[str, Any]:
    """Level 10 hedefe mesafe skoru (yüksek = daha uzak)."""
    gaps: list[float] = []
    kd = as_float(summary.get("avg_kd_ratio"))
    adr = as_float(summary.get("avg_adr"))
    if kd is not None:
        gaps.append(max(0, (cfg.TARGET_KD - kd) / cfg.TARGET_KD * 100))
    if adr is not None:
        gaps.append(max(0, (cfg.TARGET_ADR - adr) / cfg.TARGET_ADR * 100))

    rifle_first = as_float(mech.get("rifle_first_bullet_moving_pct"))
    rifle_long = as_float(mech.get("rifle_long_spray_pct"))
    starter = as_float(mech.get("starter_pistol_first_bullet_moving_pct"))
    if rifle_first is not None:
        gaps.append(max(0, (rifle_first - cfg.TARGET_RIFLE_FIRST_BULLET_MOVING) * 1.2))
    if rifle_long is not None:
        gaps.append(max(0, (rifle_long - cfg.TARGET_RIFLE_LONG_SPRAY) * 1.0))
    if starter is not None:
        gaps.append(max(0, (starter - cfg.TARGET_STARTER_PISTOL_FIRST_BULLET) * 0.8))

    usable = sum(
        1 for r in (map_stats.get("maps") or [])
        if (r.get("played") or 0) >= cfg.MAP_USABLE_MIN
    )
    if usable < 2:
        gaps.append(25)

    if not gaps:
        return metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none")

    avg_gap = sum(gaps) / len(gaps)
    return metric(clamp_score(avg_gap), source=SOURCE_DERIVED, confidence="medium")
