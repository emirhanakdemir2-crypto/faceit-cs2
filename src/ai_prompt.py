from __future__ import annotations

import json
from typing import Any

from src.config import MISSING_DATA_LABEL


def _strip_kast_if_missing(payload: dict[str, Any]) -> dict[str, Any]:
    """KAST eksikse prompt'a KAST verisi gönderme."""
    missing = payload.get("missing_fields") or []
    kast_missing = any("KAST" in str(f) for f in missing)

    summary = dict(payload.get("summary") or {})
    if kast_missing and "avg_kast" in summary:
        summary["avg_kast"] = MISSING_DATA_LABEL

    matches = []
    for m in payload.get("matches") or []:
        mc = dict(m)
        if kast_missing:
            mc.pop("kast", None)
        matches.append(mc)

    return {**payload, "summary": summary, "matches": matches[:10]}


def build_ai_context(processed_payload: dict[str, Any]) -> dict[str, Any]:
    """Ham FACEIT JSON yerine yalnızca temiz, memory-aware özet üretir."""
    memory = processed_payload.get("memory") or {}
    return {
        "profile": processed_payload.get("profile"),
        "summary": processed_payload.get("summary"),
        "recent_form": processed_payload.get("recent_form"),
        "map_stats": processed_payload.get("map_stats"),
        "data_confidence": processed_payload.get("data_confidence"),
        "period_comparison": processed_payload.get("period_comparison"),
        "period_insights": processed_payload.get("period_insights"),
        "persistent_problems": processed_payload.get("persistent_problems"),
        "new_matches_baseline": processed_payload.get("new_matches_baseline"),
        "analysis_window": processed_payload.get("analysis_window"),
        "memory": {
            "is_first_analysis": memory.get("is_first_analysis"),
            "status_message": memory.get("status_message"),
            "new_matches_count": memory.get("new_matches_count"),
            "previous_analysis_date": memory.get("previous_analysis_date"),
            "improved_areas": memory.get("improved_areas"),
            "worsened_areas": memory.get("worsened_areas"),
            "unchanged_problems": memory.get("unchanged_problems"),
            "focus_plan_7d": memory.get("focus_plan_7d"),
        },
        "missing_fields": processed_payload.get("missing_fields"),
        "generated_at": processed_payload.get("generated_at"),
    }


def build_coaching_prompt(processed_payload: dict[str, Any]) -> str:
    """Gemini'ye gönderilecek Türkçe koçluk prompt'unu üretir."""
    context = _strip_kast_if_missing(build_ai_context(processed_payload))
    profile = context.get("profile") or {}
    memory = context.get("memory") or {}
    level = profile.get("skill_level", MISSING_DATA_LABEL)
    nickname = profile.get("nickname", "Oyuncu")

    new_matches = memory.get("new_matches_count", 0)
    is_first = memory.get("is_first_analysis", True)

    memory_note = ""
    if is_first:
        memory_note = "Bu ilk analiz; baseline oluşturuluyor."
    elif new_matches == 0:
        memory_note = "Yeni maç yok, mevcut baseline korunuyor."
    else:
        memory_note = f"Son analizden bu yana {new_matches} yeni maç var."

    level_guidance = ""
    if isinstance(level, int) or (isinstance(level, str) and level.isdigit()):
        lvl = int(level)
        if lvl >= 7:
            level_guidance = (
                f"Oyuncu Level {lvl}. Basit aim tavsiyesi verme. "
                "Karar kalitesi, spacing, trade, utility timing, CT/T rol dengesi üzerine odaklan."
            )
        else:
            level_guidance = f"Oyuncu Level {lvl}. Temel mekanikler ve takım oyunu dengeli ele alınabilir."

    kast_note = ""
    missing = context.get("missing_fields") or []
    if any("KAST" in str(f) for f in missing):
        kast_note = "KAST verisi eksik — KAST üzerinden yorum yapma."

    context_json = json.dumps(context, ensure_ascii=False, indent=2)

    return f"""Sen deneyimli bir FACEIT CS2 koçusun. Aşağıdaki JSON yalnızca işlenmiş performans özetidir; ham API verisi değildir.

Oyuncu: {nickname}
Seviye: {level}
Hafıza notu: {memory_note}
{level_guidance}
{kast_note}

Kurallar:
- Türkçe yaz.
- Yalnızca verilen sayısal verilere dayan; uydurma istatistik üretme.
- Önceki analiz varsa "önceki analize göre değişim" üzerinden yorum yap.
- Yeni maç yoksa bunu açıkça belirt.
- Kısa, net ve uygulanabilir öneriler ver.

Veri:
```json
{context_json}
```

Aşağıdaki başlıklarla yanıt ver (Markdown kullan):

1. Kısa teşhis
2. Gelişen alanlar
3. Bozulan alanlar
4. Değişmeyen problemler
5. En büyük 3 hata
6. 7 günlük çalışma planı
7. Bir sonraki maçlarda takip edilecek 3 metrik
"""
