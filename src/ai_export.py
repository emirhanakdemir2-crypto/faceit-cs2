from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.ai_prompt import build_ai_context


def build_ai_export_markdown(processed_payload: dict[str, Any]) -> str:
    """ChatGPT/Gemini/Claude'a yapıştırılabilir AI export belgesi."""
    profile = processed_payload.get("profile") or {}
    nickname = profile.get("nickname", "oyuncu")
    window = processed_payload.get("analysis_window") or {}
    days = window.get("days", 90)
    matches = window.get("analyzed_matches", processed_payload.get("summary", {}).get("total_matches"))

    context = build_ai_context(processed_payload)
    context["period_comparison"] = processed_payload.get("period_comparison")
    context["period_insights"] = processed_payload.get("period_insights")
    context["persistent_problems"] = processed_payload.get("persistent_problems")
    context["new_matches_baseline"] = processed_payload.get("new_matches_baseline")
    context["analysis_window"] = window

    context_json = json.dumps(context, ensure_ascii=False, indent=2)

    return f"""# FACEIT CS2 AI Koçluk Export — {nickname}

Bu belge ham FACEIT JSON içermez; yalnızca işlenmiş metrikler ve hafıza bağlamı içerir.
ChatGPT, Gemini veya Claude'a yapıştırıp koçluk yorumu isteyebilirsiniz.

## Görev

Son {days} gün / {matches} maç performansını analiz et.
Önceki analizle gelişim/gerilemeyi değerlendir.
7 günlük odak planı ve takip edilecek 3 metrik öner.

## Kurallar

- Türkçe yanıt ver.
- Yalnızca aşağıdaki veriye dayan; uydurma istatistik üretme.
- KAST eksikse KAST yorumu yapma.
- Level 8+ oyuncuya basit aim tavsiyesi verme.
- Counter-strafe/spray için demo verisi yoksa bunu belirt.

## İşlenmiş Veri

```json
{context_json}
```

## İstenen Çıktı Formatı

1. Kısa teşhis (90 günlük perspektif)
2. Gelişen alanlar (önceki analize göre)
3. Bozulan alanlar
4. Değişmeyen problemler
5. En büyük 3 hata
6. 7 günlük çalışma planı
7. Sonraki maçlarda takip edilecek 3 metrik

---

*Oluşturulma: {processed_payload.get('generated_at', '—')}*
"""


def write_ai_export(nickname: str, processed_payload: dict[str, Any], export_dir: Path) -> Path:
    """data/ai_exports/{nickname}_ai_prompt_latest.md dosyasını yazar."""
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"{nickname.lower()}_ai_prompt_latest.md"
    path.write_text(build_ai_export_markdown(processed_payload), encoding="utf-8")
    return path
