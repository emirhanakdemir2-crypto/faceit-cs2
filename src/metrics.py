from __future__ import annotations

from typing import Any

import pandas as pd

from src.config import MISSING_DATA_LABEL


def _numeric_series(matches: list[dict[str, Any]], field: str) -> pd.Series:
    values = []
    for match in matches:
        raw = match.get(field)
        if raw is None or raw == MISSING_DATA_LABEL:
            values.append(None)
        else:
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                values.append(None)
    return pd.Series(values, dtype="float64")


def _mean_or_missing(series: pd.Series, decimals: int = 2) -> float | str:
    clean = series.dropna()
    if clean.empty:
        return MISSING_DATA_LABEL
    return round(float(clean.mean()), decimals)


def _sum_or_missing(series: pd.Series) -> int | str:
    clean = series.dropna()
    if clean.empty:
        return MISSING_DATA_LABEL
    return int(clean.sum())


def _empty_summary() -> dict[str, Any]:
    return {
        "total_matches": 0,
        "matches_with_stats": 0,
        "wins": MISSING_DATA_LABEL,
        "losses": MISSING_DATA_LABEL,
        "win_rate_pct": MISSING_DATA_LABEL,
        "avg_kills": MISSING_DATA_LABEL,
        "avg_deaths": MISSING_DATA_LABEL,
        "avg_assists": MISSING_DATA_LABEL,
        "avg_kd_ratio": MISSING_DATA_LABEL,
        "avg_kr_ratio": MISSING_DATA_LABEL,
        "avg_adr": MISSING_DATA_LABEL,
        "avg_headshot_pct": MISSING_DATA_LABEL,
        "avg_kast": MISSING_DATA_LABEL,
        "total_mvps": MISSING_DATA_LABEL,
        "total_triple_kills": MISSING_DATA_LABEL,
        "total_quadro_kills": MISSING_DATA_LABEL,
        "total_penta_kills": MISSING_DATA_LABEL,
        "best_kd_match_id": MISSING_DATA_LABEL,
        "best_kd_value": MISSING_DATA_LABEL,
        "worst_kd_match_id": MISSING_DATA_LABEL,
        "worst_kd_value": MISSING_DATA_LABEL,
    }


def compute_performance_summary(
    normalized: dict[str, Any] | None = None,
    *,
    matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Dönem veya tam set için performans özetini hesaplar."""
    if matches is None:
        matches = (normalized or {}).get("matches") or []
    total = len(matches)

    if total == 0:
        return _empty_summary()

    with_stats = [m for m in matches if m.get("stats_available")]
    wins = sum(1 for m in matches if m.get("won") is True)
    losses = sum(1 for m in matches if m.get("won") is False)
    decided = wins + losses

    kills = _numeric_series(with_stats, "kills")
    deaths = _numeric_series(with_stats, "deaths")
    assists = _numeric_series(with_stats, "assists")
    kd = _numeric_series(with_stats, "kd_ratio")
    kr = _numeric_series(with_stats, "kr_ratio")
    adr = _numeric_series(with_stats, "adr")
    hs_pct = _numeric_series(with_stats, "headshot_pct")
    kast = _numeric_series(with_stats, "kast")
    mvps = _numeric_series(with_stats, "mvps")
    triple = _numeric_series(with_stats, "triple_kills")
    quadro = _numeric_series(with_stats, "quadro_kills")
    penta = _numeric_series(with_stats, "penta_kills")

    best_kd_idx = kd.idxmax() if kd.notna().any() else None
    worst_kd_idx = kd.idxmin() if kd.notna().any() else None

    def _match_id_at(idx: int | None) -> str:
        if idx is None:
            return MISSING_DATA_LABEL
        try:
            return with_stats[int(idx)].get("match_id", MISSING_DATA_LABEL)
        except (IndexError, TypeError):
            return MISSING_DATA_LABEL

    return {
        "total_matches": total,
        "matches_with_stats": len(with_stats),
        "wins": wins if decided else MISSING_DATA_LABEL,
        "losses": losses if decided else MISSING_DATA_LABEL,
        "win_rate_pct": (
            round(wins / decided * 100, 1) if decided > 0 else MISSING_DATA_LABEL
        ),
        "avg_kills": _mean_or_missing(kills),
        "avg_deaths": _mean_or_missing(deaths),
        "avg_assists": _mean_or_missing(assists),
        "avg_kd_ratio": _mean_or_missing(kd),
        "avg_kr_ratio": _mean_or_missing(kr),
        "avg_adr": _mean_or_missing(adr),
        "avg_headshot_pct": _mean_or_missing(hs_pct),
        "avg_kast": _mean_or_missing(kast),
        "total_mvps": _sum_or_missing(mvps),
        "total_triple_kills": _sum_or_missing(triple),
        "total_quadro_kills": _sum_or_missing(quadro),
        "total_penta_kills": _sum_or_missing(penta),
        "best_kd_match_id": _match_id_at(best_kd_idx),
        "best_kd_value": (
            round(float(kd.loc[best_kd_idx]), 2)
            if best_kd_idx is not None and pd.notna(kd.loc[best_kd_idx])
            else MISSING_DATA_LABEL
        ),
        "worst_kd_match_id": _match_id_at(worst_kd_idx),
        "worst_kd_value": (
            round(float(kd.loc[worst_kd_idx]), 2)
            if worst_kd_idx is not None and pd.notna(kd.loc[worst_kd_idx])
            else MISSING_DATA_LABEL
        ),
    }


MIN_MAP_MATCHES_FOR_VERDICT = 3


def compute_recent_form(normalized: dict[str, Any], count: int = 5) -> dict[str, Any]:
    """Son N maçlık form özeti."""
    matches = normalized.get("matches") or []
    recent = matches[:count]

    if not recent:
        return {
            "match_count": 0,
            "record": MISSING_DATA_LABEL,
            "wins": MISSING_DATA_LABEL,
            "losses": MISSING_DATA_LABEL,
            "win_rate_pct": MISSING_DATA_LABEL,
            "avg_kd_ratio": MISSING_DATA_LABEL,
            "avg_adr": MISSING_DATA_LABEL,
            "streak": MISSING_DATA_LABEL,
            "streak_comment": MISSING_DATA_LABEL,
            "best_match": MISSING_DATA_LABEL,
            "worst_match": MISSING_DATA_LABEL,
            "riskiest_map": MISSING_DATA_LABEL,
            "matches": [],
        }

    with_stats = [m for m in recent if m.get("stats_available")]
    wins = sum(1 for m in recent if m.get("won") is True)
    losses = sum(1 for m in recent if m.get("won") is False)
    decided = wins + losses

    kd = _numeric_series(with_stats, "kd_ratio")
    adr = _numeric_series(with_stats, "adr")

    streak_chars: list[str] = []
    for m in recent:
        if m.get("won") is True:
            streak_chars.append("W")
        elif m.get("won") is False:
            streak_chars.append("L")
        else:
            streak_chars.append("?")

    form_matches = []
    for m in recent:
        form_matches.append(
            {
                "match_id": m.get("match_id"),
                "map": m.get("map"),
                "won": m.get("won"),
                "kd_ratio": m.get("kd_ratio"),
                "adr": m.get("adr"),
                "finished_at": m.get("finished_at"),
            }
        )

    best_match = MISSING_DATA_LABEL
    worst_match = MISSING_DATA_LABEL
    riskiest_map = MISSING_DATA_LABEL

    scored = [
        m for m in form_matches
        if m.get("kd_ratio") not in (None, MISSING_DATA_LABEL)
    ]
    if scored:
        best = max(scored, key=lambda m: float(m["kd_ratio"]))
        worst = min(scored, key=lambda m: float(m["kd_ratio"]))
        best_match = (
            f"{best.get('map')} (K/D {best.get('kd_ratio')}, {_result_short(best.get('won'))})"
        )
        worst_match = (
            f"{worst.get('map')} (K/D {worst.get('kd_ratio')}, {_result_short(worst.get('won'))})"
        )

    map_losses: dict[str, int] = {}
    for m in recent:
        mp = m.get("map")
        if mp and mp != MISSING_DATA_LABEL and m.get("won") is False:
            map_losses[mp] = map_losses.get(mp, 0) + 1
    if map_losses:
        riskiest_map = max(map_losses, key=map_losses.get)

    streak_comment = _streak_comment(streak_chars, losses)

    return {
        "match_count": len(recent),
        "record": f"{wins}W-{losses}L" if decided else MISSING_DATA_LABEL,
        "wins": wins if decided else MISSING_DATA_LABEL,
        "losses": losses if decided else MISSING_DATA_LABEL,
        "win_rate_pct": (
            round(wins / decided * 100, 1) if decided > 0 else MISSING_DATA_LABEL
        ),
        "avg_kd_ratio": _mean_or_missing(kd),
        "avg_adr": _mean_or_missing(adr),
        "streak": " ".join(streak_chars) if streak_chars else MISSING_DATA_LABEL,
        "streak_comment": streak_comment,
        "best_match": best_match,
        "worst_match": worst_match,
        "riskiest_map": riskiest_map,
        "matches": form_matches,
    }


def _result_short(won: bool | None) -> str:
    if won is True:
        return "W"
    if won is False:
        return "L"
    return "?"


def _streak_comment(streak_chars: list[str], losses: int) -> str:
    if not streak_chars:
        return MISSING_DATA_LABEL
    if losses >= 3:
        return "Kısa vadeli form düşüşü var; üst üste loss sonrası queue devamı riskli."
    if streak_chars[0] == "W":
        return "Son maç galibiyet — momentum korunabilir."
    if all(c == "W" for c in streak_chars):
        return "Tüm son maçlar galibiyet — form yüksek."
    return "Karışık form — tutarlılık için rol ve iletişim öncelikli."


def compute_map_stats(normalized: dict[str, Any]) -> dict[str, Any]:
    """Harita bazlı win/loss tablosu ve en iyi / en zayıf harita."""
    matches = normalized.get("matches") or []
    by_map: dict[str, dict[str, int]] = {}

    for match in matches:
        map_name = match.get("map")
        if not map_name or map_name == MISSING_DATA_LABEL:
            continue
        if map_name not in by_map:
            by_map[map_name] = {"wins": 0, "losses": 0, "unknown": 0, "total": 0}
        by_map[map_name]["total"] += 1
        won = match.get("won")
        if won is True:
            by_map[map_name]["wins"] += 1
        elif won is False:
            by_map[map_name]["losses"] += 1
        else:
            by_map[map_name]["unknown"] += 1

    table: list[dict[str, Any]] = []
    for map_name, stats in sorted(by_map.items(), key=lambda x: -x[1]["total"]):
        decided = stats["wins"] + stats["losses"]
        wr = round(stats["wins"] / decided * 100, 1) if decided > 0 else MISSING_DATA_LABEL
        table.append(
            {
                "map": map_name,
                "played": stats["total"],
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate_pct": wr,
            }
        )

    best_map = MISSING_DATA_LABEL
    worst_map = MISSING_DATA_LABEL
    map_verdict_note = MISSING_DATA_LABEL

    eligible = [
        r for r in table
        if r["played"] >= MIN_MAP_MATCHES_FOR_VERDICT
        and r["win_rate_pct"] != MISSING_DATA_LABEL
    ]

    if len(eligible) >= 2:
        best = max(eligible, key=lambda r: (r["win_rate_pct"], r["played"]))
        worst = min(eligible, key=lambda r: (r["win_rate_pct"], -r["played"]))
        if best["map"] != worst["map"]:
            best_map = best["map"]
            worst_map = worst["map"]
        else:
            sorted_maps = sorted(eligible, key=lambda r: r["win_rate_pct"])
            best_map = sorted_maps[-1]["map"]
            worst_map = sorted_maps[0]["map"]
            if best_map == worst_map and len(sorted_maps) > 1:
                worst_map = sorted_maps[1]["map"]
    elif eligible:
        map_verdict_note = "Harita bazlı kesin yorum için veri yetersiz (harita başına min. 3 maç, en az 2 harita gerekli)."
    else:
        map_verdict_note = "Harita bazlı kesin yorum için veri yetersiz (harita başına min. 3 maç gerekli)."

    return {
        "maps": table,
        "best_map": best_map,
        "worst_map": worst_map,
        "map_verdict_note": map_verdict_note,
    }


def collect_missing_fields(normalized: dict[str, Any]) -> list[str]:
    """Raporda veri eksik olan alanları listeler."""
    missing: list[str] = []

    profile = normalized.get("profile") or {}
    profile_labels = {
        "country": "Profil — ülke",
        "skill_level": "Profil — skill level",
        "faceit_elo": "Profil — ELO",
        "game_player_name": "Profil — oyun adı",
        "faceit_url": "Profil — URL",
    }
    for key, label in profile_labels.items():
        if profile.get(key) in (None, "", MISSING_DATA_LABEL):
            missing.append(label)

    for index, match in enumerate(normalized.get("matches") or [], start=1):
        prefix = f"Maç #{index} ({match.get('match_id', '?')})"
        if not match.get("stats_available"):
            missing.append(f"{prefix} — maç istatistikleri")
        if match.get("map") in (None, "", MISSING_DATA_LABEL):
            missing.append(f"{prefix} — harita")
        for field, label in (
            ("kd_ratio", "K/D"),
            ("adr", "ADR"),
            ("headshot_pct", "Headshot %"),
            ("kast", "KAST"),
        ):
            if match.get(field) in (None, "", MISSING_DATA_LABEL) and match.get("stats_available"):
                missing.append(f"{prefix} — {label}")

    return missing


def compute_data_confidence(
    total_matches: int,
    missing_fields: list[str],
    *,
    days: int = 90,
) -> dict[str, Any]:
    """Örneklem büyüklüğüne göre veri güven seviyesi (90 günlük analiz odaklı)."""
    if total_matches >= 80:
        level = "Daha güvenilir"
        detail = (
            f"{total_matches} maç / {days} gün — dönemsel trend ve harita havuzu yorumları anlamlı."
        )
    elif total_matches >= 40:
        level = "Orta güven"
        detail = (
            f"{total_matches} maç / {days} gün — genel eğilimler görülebilir; "
            "harita bazlı kesin yorum için daha fazla örnek gerekebilir."
        )
    else:
        level = "Düşük güven"
        detail = (
            f"{total_matches} maç / {days} gün — erken örneklem; "
            "90 günlük kararlar için daha fazla maç toplanmalı."
        )

    notes: list[str] = []
    if total_matches < 120:
        notes.append(
            f"İstenen 120 maça karşı {total_matches} maç analiz edildi — "
            "oyun sıklığına bağlı olarak pencere dolmamış olabilir."
        )
    kast_missing = any("KAST" in f for f in missing_fields)
    if kast_missing:
        notes.append("KAST verisi eksik — round katkı metrikleri sınırlı.")

    stats_missing = any("istatistikleri" in f for f in missing_fields)
    if stats_missing:
        notes.append("Bazı maçlarda istatistik alınamadı — ortalamalar çarpıtılabilir.")

    notes.append(
        "Counter-strafe ve spray metrikleri FACEIT API'den gelmez; demo analizi gerekir."
    )

    if len(notes) == 1 and "Counter-strafe" in notes[0]:
        notes.insert(0, "Kritik eksik alan tespit edilmedi.")

    return {
        "level": level,
        "detail": detail,
        "notes": notes,
        "match_count": total_matches,
        "days": days,
    }


def compute_persistent_problems(
    summary: dict[str, Any],
    period_data: dict[str, Any],
    memory: dict[str, Any],
) -> list[str]:
    """Tekrarlayan / kalıcı problemleri listeler."""
    problems: list[str] = []

    def _f(val: Any) -> float | None:
        if val in (None, MISSING_DATA_LABEL):
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    wr = _f(summary.get("win_rate_pct"))
    if wr is not None and wr < 45:
        problems.append(f"Dönem genelinde düşük kazanma oranı ({wr}%).")

    kd = _f(summary.get("avg_kd_ratio"))
    if kd is not None and kd < 1.0:
        problems.append(f"Dönem genelinde K/D 1.0 altında ({kd}).")

    for key in ("first_30_days", "middle_30_days", "last_30_days"):
        ps = period_data.get(key, {}).get("summary", {})
        pwr = _f(ps.get("win_rate_pct"))
        if pwr is not None and pwr < 40:
            label = period_data.get(key, {}).get("label", key)
            problems.append(f"{label}: düşük kazanma oranı ({pwr}%).")

    for item in memory.get("unchanged_problems") or []:
        if item not in problems:
            problems.append(item)

    if not problems:
        problems.append("Belirgin kalıcı problem tespit edilmedi.")
    return problems


def compute_new_matches_baseline(
    matches: list[dict[str, Any]],
    new_match_ids: list[str],
    baseline_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Yeni maçların önceki dönem baseline'ına göre performansını kıyaslar."""
    if not new_match_ids:
        return {
            "has_new": False,
            "message": "Yeni maç yok — baseline korunuyor.",
            "insights": [],
        }

    new_only = [m for m in matches if m.get("match_id") in new_match_ids]
    new_summary = compute_performance_summary(matches=new_only)

    if not baseline_summary:
        return {
            "has_new": True,
            "new_count": len(new_match_ids),
            "new_summary": new_summary,
            "message": "İlk analiz — yeni maçlar için baseline kıyaslaması yok.",
            "insights": [],
        }

    insights: list[str] = []
    pairs = [
        ("Kazanma oranı", "win_rate_pct", 3.0),
        ("K/D", "avg_kd_ratio", 0.05),
        ("ADR", "avg_adr", 3.0),
    ]
    for label, key, threshold in pairs:
        try:
            n = new_summary.get(key)
            b = baseline_summary.get(key)
            if n in (None, MISSING_DATA_LABEL) or b in (None, MISSING_DATA_LABEL):
                continue
            nf, bf = float(n), float(b)
            diff = nf - bf
            if abs(diff) >= threshold:
                direction = "üzerinde" if diff > 0 else "altında"
                insights.append(
                    f"Yeni maçlarda {label} baseline'ın {direction} ({bf} → {nf})."
                )
        except (TypeError, ValueError):
            continue

    if not insights:
        insights.append("Yeni maçlar baseline ile benzer performans gösteriyor.")

    return {
        "has_new": True,
        "new_count": len(new_match_ids),
        "new_summary": new_summary,
        "message": f"{len(new_match_ids)} yeni maç baseline ile kıyaslandı.",
        "insights": insights,
    }
