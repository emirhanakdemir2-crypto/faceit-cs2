from __future__ import annotations

from typing import Any

from src import suite_config as cfg
from src.suite_common import clamp_score


def compute_unnecessary_death_score(metrics: dict[str, Any]) -> int | str:
    """0–100 skor; yüksek = daha iyi ölüm kalitesi."""
    if not metrics.get("reliable"):
        return "unavailable"

    score = 100.0
    early = metrics.get("early_death_pct")
    untraded = metrics.get("untraded_death_pct")
    dak5 = metrics.get("death_after_kill_within_5s_pct")
    adv = metrics.get("deaths_when_team_advantage")

    if isinstance(early, (int, float)):
        if early > cfg.EARLY_DEATH_WEAK:
            score -= min(35, (early - cfg.EARLY_DEATH_OKAY) * 1.5)
        elif early > cfg.EARLY_DEATH_OKAY:
            score -= 10
    if isinstance(untraded, (int, float)):
        if untraded > cfg.UNTRADED_DEATH_WEAK:
            score -= min(30, (untraded - cfg.UNTRADED_DEATH_OKAY) * 0.8)
        elif untraded > cfg.UNTRADED_DEATH_OKAY:
            score -= 12
    if isinstance(dak5, (int, float)):
        if dak5 > 25:
            score -= min(20, dak5 * 0.5)
    if isinstance(adv, (int, float)) and adv > 0:
        total = metrics.get("total_deaths") or 1
        adv_pct = adv / total * 100 if total else 0
        if adv_pct > 15:
            score -= min(15, adv_pct * 0.6)

    return clamp_score(score)


def generate_death_quality_commentary(metrics: dict[str, Any]) -> list[str]:
    if not metrics.get("reliable"):
        return ["Impact / Death Quality için yeterli demo event verisi yok."]

    notes: list[str] = []
    untraded = metrics.get("untraded_death_pct")
    early = metrics.get("early_death_pct")
    dak5 = metrics.get("death_after_kill_within_5s_pct")
    adv = metrics.get("deaths_when_team_advantage")
    total = metrics.get("total_deaths") or 0

    if isinstance(untraded, (int, float)) and untraded > cfg.UNTRADED_DEATH_OKAY:
        notes.append("Ölümler genelde trade edilemiyor.")
    if isinstance(early, (int, float)) and early > cfg.EARLY_DEATH_OKAY:
        notes.append("Erken ölüm oranı yüksek.")
    if isinstance(dak5, (int, float)) and dak5 > 20:
        notes.append("Kill sonrası reset zayıf.")
    if isinstance(adv, (int, float)) and total and adv / total * 100 > 12:
        notes.append("Avantajdayken gereksiz ölüm var.")

    uds = metrics.get("unnecessary_death_score")
    if isinstance(uds, int) and uds < 55:
        notes.append("Genel ölüm kalitesi zayıf (Unnecessary Death Score düşük).")

    if not notes:
        notes.append("Belirgin death quality sinyali yok.")
    return notes


def generate_opening_commentary(metrics: dict[str, Any]) -> list[str]:
    if not metrics.get("reliable"):
        return []
    notes: list[str] = []
    success = metrics.get("opening_duel_success_pct")
    attempts = metrics.get("opening_duel_attempts") or 0
    rounds = metrics.get("rounds_analyzed") or 1
    odeaths = metrics.get("opening_deaths") or 0

    if isinstance(success, (int, float)):
        if success < cfg.OPENING_DUEL_WEAK:
            notes.append("Opening duel kalitesi zayıf.")
        elif success >= cfg.OPENING_DUEL_GOOD:
            notes.append("Opening duel başarısı iyi.")
    if odeaths > rounds * 0.35:
        notes.append("İlk temaslarda gereksiz risk var.")
    if attempts < rounds * 0.15:
        notes.append("Opening rolü düşük; 2nd entry/trade rolüne yakın.")
    return notes


def generate_trade_commentary(metrics: dict[str, Any]) -> list[str]:
    if not metrics.get("reliable"):
        return []
    notes: list[str] = []
    untraded = metrics.get("untraded_death_pct")
    tk = metrics.get("trade_kills") or 0

    if isinstance(untraded, (int, float)) and untraded > cfg.UNTRADED_DEATH_WEAK:
        notes.append("Yalnız ölümler fazla.")
    if tk >= 5:
        notes.append("2nd entry/trade rolü iyi çalışıyor.")
    elif isinstance(untraded, (int, float)) and untraded > 45:
        notes.append("Takım trade mesafesinde değil veya fazla yalnız oynanıyor.")
    return notes


def generate_impact_commentary(
    impact_metrics: dict[str, Any],
    faceit_kd: float | None = None,
    faceit_wr: float | None = None,
) -> list[str]:
    if not impact_metrics.get("reliable"):
        return []
    notes: list[str] = []
    rating = impact_metrics.get("impact_rating_0_100")
    untraded = impact_metrics.get("untraded_death_pct")

    if isinstance(rating, (int, float)) and rating < cfg.IMPACT_RATING_OKAY:
        if faceit_kd and faceit_kd >= 1.1:
            notes.append("K/D iyi ama impact düşük — geç kill / düşük round etkisi.")
        if isinstance(untraded, (int, float)) and untraded > cfg.UNTRADED_DEATH_OKAY:
            notes.append("Impact düşük ve untraded death yüksek — karar/pozisyon problemi.")
    if (
        isinstance(rating, (int, float)) and rating >= cfg.IMPACT_RATING_GOOD
        and faceit_wr is not None and faceit_wr < 48
    ):
        notes.append("Impact yüksek ama win düşük — takım conversion veya map sorunları.")

    return notes
