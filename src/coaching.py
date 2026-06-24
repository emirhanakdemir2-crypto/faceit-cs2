from __future__ import annotations

from typing import Any

from src.config import MISSING_DATA_LABEL


def _is_number(value: Any) -> bool:
    if value is None or value == MISSING_DATA_LABEL:
        return False
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _skill_level(profile: dict[str, Any]) -> int | None:
    raw = profile.get("skill_level")
    if raw in (None, "", MISSING_DATA_LABEL):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _is_high_level(level: int | None) -> bool:
    return level is not None and level >= 7


def generate_coaching_draft(
    profile: dict[str, Any],
    summary: dict[str, Any],
    form: dict[str, Any],
    map_stats: dict[str, Any],
) -> dict[str, Any]:
    """
    Level 5–9 oyuncular için kural tabanlı koçluk yorum taslağı.
    Claude API çağrısı yapılmaz; yalnızca rapor formatı hazırlanır.
    """
    level = _skill_level(profile)
    nickname = profile.get("nickname") or "Oyuncu"
    eligible = level is not None and 5 <= level <= 9

    if not eligible:
        return {
            "applicable": False,
            "skill_level": level if level is not None else MISSING_DATA_LABEL,
            "headline": "Koçluk yorumu bu seviye için hazırlanmadı",
            "sections": [
                {
                    "title": "Kapsam",
                    "body": (
                        "Bu taslak yalnızca FACEIT Level 5–9 oyuncuları için üretilir. "
                        f"Mevcut seviye: {_fmt_level(level)}."
                    ),
                }
            ],
        }

    strengths: list[str] = []
    weaknesses: list[str] = []
    focus: list[str] = []

    avg_kd = summary.get("avg_kd_ratio")
    avg_adr = summary.get("avg_adr")
    avg_hs = summary.get("avg_headshot_pct")
    avg_kast = summary.get("avg_kast")
    win_rate = summary.get("win_rate_pct")

    high_level = _is_high_level(level)

    # Win rate düşük ama ADR/K/D iyi
    if (
        _is_number(win_rate)
        and float(win_rate) < 45
        and _is_number(avg_adr)
        and float(avg_adr) >= 75
        and _is_number(avg_kd)
        and float(avg_kd) >= 1.0
    ):
        weaknesses.append(
            "Bireysel hasar katkısı var fakat round kazanımına dönüşmüyor. "
            "Problem aimden çok karar kalitesi, trade, timing, utility veya takım uyumu olabilir."
        )
        focus.append(
            "Round planı: entry sonrası trade zinciri, post-plant ve retake kararlarını demo ile incele."
        )
        focus.append("Utility timing — execute öncesi smoke/molly senkronu ve spacing kontrolü.")

    # Son 5 maçta 3+ loss
    form_losses = form.get("losses")
    if _is_number(form_losses) and int(form_losses) >= 3:
        weaknesses.append(
            "Kısa vadeli form düşüşü var; üst üste loss sonrası queue devamı riskli."
        )
        focus.append("3+ loss sonrası 20–30 dk mola veya scrim/warmup ile devam et.")

    # HS iyi ama win rate düşük
    if (
        _is_number(avg_hs)
        and float(avg_hs) >= 42
        and _is_number(win_rate)
        and float(win_rate) < 45
    ):
        weaknesses.append(
            "Aim seviyesi yeterli görünüyor; utility, trade, round sonu kararları "
            "ve mid-round karar kalitesi çalışılmalı."
        )
        if high_level:
            focus.append("Mid-round default okuma: info paylaşımı ve rotate timing.")
        else:
            focus.append("Trade pozisyonu ve takım execute'una uyum.")

    if _is_number(avg_kd) and float(avg_kd) >= 1.15:
        strengths.append(f"K/D ortalaması güçlü ({avg_kd}) — duel ve trade etkinliği iyi.")
    elif _is_number(avg_kd) and float(avg_kd) < 0.95:
        weaknesses.append(f"K/D ortalaması düşük ({avg_kd}) — gereksiz peek ve erken ölüm riski.")
        if high_level:
            focus.append("Spacing ve angle advantage: fight açmadan önce crossfire kur.")
        else:
            focus.append("Pozisyon almadan fight açmamayı ve trade ağına güvenmeyi çalış.")

    if _is_number(avg_adr) and float(avg_adr) >= 80:
        strengths.append(f"ADR yüksek ({avg_adr}) — round başına hasar katkısı iyi.")
    elif _is_number(avg_adr) and float(avg_adr) < 70:
        weaknesses.append(f"ADR düşük ({avg_adr}) — round'larda yeterli hasar bırakılmıyor.")
        focus.append("Default pozisyonlarda utility ile alan açarak hasar üretmeye odaklan.")

    if _is_number(avg_hs) and float(avg_hs) >= 45:
        strengths.append(f"Headshot oranı iyi ({avg_hs}%).")
    elif _is_number(avg_hs) and float(avg_hs) < 38 and not high_level:
        weaknesses.append(f"Headshot oranı geliştirilebilir ({avg_hs}%).")
        focus.append("Crosshair placement drill — Level 7+ için aim rutini yerine pre-aim pozisyonları.")

    if _is_number(avg_kast) and float(avg_kast) >= 70:
        strengths.append(f"KAST sağlam ({avg_kast}%) — round'lara katkı tutarlı.")
    elif _is_number(avg_kast) and float(avg_kast) < 65:
        weaknesses.append(f"KAST düşük ({avg_kast}%) — round etkisi sınırlı.")
        focus.append("Ölmeden info, assist veya clutch denemesiyle round'a değer kat.")

    if _is_number(win_rate) and float(win_rate) >= 55:
        strengths.append(f"Son dönem kazanma oranı pozitif ({win_rate}%).")
    elif _is_number(win_rate) and float(win_rate) < 45:
        if not any("round kazanımına" in w for w in weaknesses):
            weaknesses.append(f"Kazanma oranı düşük ({win_rate}%).")
        if high_level:
            focus.append("CT/T rol dengesi: hangi round'larda space, hangilerinde info/anchor oynadığını netleştir.")
        else:
            focus.append("Stack ile rol netliği (entry/support) belirle.")

    best_map = map_stats.get("best_map")
    worst_map = map_stats.get("worst_map")
    map_note = map_stats.get("map_verdict_note")
    if best_map and best_map != MISSING_DATA_LABEL and not map_note:
        strengths.append(f"En güçlü harita (3+ maç): {best_map} — bu haritada güvenli pick.")
    if (
        worst_map
        and worst_map != MISSING_DATA_LABEL
        and worst_map != best_map
        and not map_note
    ):
        weaknesses.append(f"En zayıf harita (3+ maç): {worst_map} — demo incelemesi önerilir.")
        focus.append(f"{worst_map} için default setup, rotasyon ve mid-round kararlarını gözden geçir.")

    if high_level and not focus:
        focus.append("Karar kalitesi: hangi duel'leri alıp hangilerinden kaçındığını maç sonu not et.")

    if not strengths:
        strengths.append("Temel istatistikler sınırlı; daha fazla maç verisiyle güçlü yönler netleşir.")
    if not weaknesses:
        weaknesses.append("Belirgin zayıf alan tespit edilmedi; tutarlılık korunmalı.")
    if not focus:
        focus.append("Mevcut güçlü yönleri koruyarak harita havuzunu daralt.")

    return {
        "applicable": True,
        "skill_level": level,
        "headline": f"Level {level} — {nickname} için koçluk taslağı",
        "sections": [
            {"title": "Güçlü Yönler", "items": strengths},
            {"title": "Geliştirilmesi Gerekenler", "items": weaknesses},
            {"title": "Öncelikli Çalışma Alanları", "items": focus},
            {
                "title": "AI Koçluk Notu",
                "body": (
                    "_Bu bölüm kural tabanlı taslaktır. Claude API entegrasyonu "
                    "aktifleştirildiğinde kişiselleştirilmiş yorum buraya eklenecek._"
                ),
            },
        ],
    }


def _fmt_level(level: int | None) -> str:
    if level is None:
        return MISSING_DATA_LABEL
    return str(level)
