from __future__ import annotations

from typing import Any

from src.config import MISSING_DATA_LABEL


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return MISSING_DATA_LABEL
    return str(value)


def _result_label(won: bool | None) -> str:
    if won is True:
        return "W"
    if won is False:
        return "L"
    return "?"


def _render_coaching_section(coaching: dict[str, Any]) -> list[str]:
    lines = [
        "## Koçluk Yorum Taslağı (Level 5–9)",
        "",
        f"**{_fmt(coaching.get('headline'))}**",
        "",
    ]

    for section in coaching.get("sections") or []:
        title = section.get("title", "")
        lines.append(f"### {title}")
        lines.append("")
        if "body" in section:
            lines.append(section["body"])
            lines.append("")
        for item in section.get("items") or []:
            lines.append(f"- {item}")
        if section.get("items"):
            lines.append("")

    return lines


def _render_memory_section(memory: dict[str, Any]) -> list[str]:
    lines = [
        "## Hafıza Durumu",
        "",
        f"**{_fmt(memory.get('status_message'))}**",
        "",
        "| Alan | Değer |",
        "| --- | --- |",
        f"| Toplam kayıtlı maç | {_fmt(memory.get('stored_matches_total'))} |",
        f"| Son analizden sonra yeni maç | {_fmt(memory.get('new_matches_count'))} |",
        f"| Önceki analiz tarihi | {_fmt(memory.get('previous_analysis_date'))} |",
        "",
        "### Önceki Analize Göre Gelişen Alanlar",
        "",
    ]
    for item in memory.get("improved_areas") or []:
        lines.append(f"- {item}")
    if not memory.get("improved_areas"):
        lines.append(f"- {MISSING_DATA_LABEL}")

    lines.extend(["", "### Önceki Analize Göre Kötüleşen Alanlar", ""])
    for item in memory.get("worsened_areas") or []:
        lines.append(f"- {item}")
    if not memory.get("worsened_areas"):
        lines.append(f"- {MISSING_DATA_LABEL}")

    lines.extend(["", "### Değişmeyen Problemler", ""])
    for item in memory.get("unchanged_problems") or []:
        lines.append(f"- {item}")
    if not memory.get("unchanged_problems"):
        lines.append("- Belirgin sabit problem tespit edilmedi.")

    lines.extend(["", "### Önceki Önerilerin Durumu", ""])
    recs = memory.get("recommendation_status") or []
    if recs:
        for rec in recs:
            lines.append(
                f"- [{_fmt(rec.get('status'))}] {_fmt(rec.get('problem_area'))}: "
                f"{_fmt(rec.get('recommendation'))}"
            )
    else:
        lines.append("- Önceki analiz veya açık öneri bulunamadı.")

    lines.extend(["", "### Yeni 7 Günlük Odak Planı", ""])
    lines.append("| Gün | Odak |")
    lines.append("| --- | --- |")
    for day in memory.get("focus_plan_7d") or []:
        lines.append(f"| {_fmt(day.get('day'))} | {_fmt(day.get('focus'))} |")

    lines.append("")
    return lines


def _render_data_confidence(confidence: dict[str, Any]) -> list[str]:
    lines = [
        "## Veri Güveni",
        "",
        f"**Seviye: {_fmt(confidence.get('level'))}**",
        "",
        _fmt(confidence.get("detail")),
        "",
        "**Notlar:**",
        "",
    ]
    for note in confidence.get("notes") or []:
        lines.append(f"- {note}")
    lines.append("")
    return lines


def write_markdown_report(
    normalized: dict[str, Any],
    summary: dict[str, Any],
    *,
    form: dict[str, Any] | None = None,
    map_stats: dict[str, Any] | None = None,
    missing_fields: list[str] | None = None,
    coaching: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
    confidence: dict[str, Any] | None = None,
) -> str:
    """Normalize edilmiş veri ve özetten Markdown rapor metni üretir."""
    profile = normalized.get("profile") or {}
    matches = normalized.get("matches") or []
    nickname = normalized.get("nickname") or profile.get("nickname") or "oyuncu"
    errors = normalized.get("collection_errors") or []
    form = form or {}
    map_stats = map_stats or {
        "maps": [],
        "best_map": MISSING_DATA_LABEL,
        "worst_map": MISSING_DATA_LABEL,
        "map_verdict_note": MISSING_DATA_LABEL,
    }
    missing_fields = missing_fields or []
    coaching = coaching or {}
    memory = memory or {}
    confidence = confidence or {}

    lines: list[str] = [
        f"# FACEIT CS2 Performans Raporu — {_fmt(nickname)}",
        "",
        f"*Oluşturulma: {normalized.get('generated_at', MISSING_DATA_LABEL)}*",
        "",
    ]

    if memory:
        lines.extend(_render_memory_section(memory))

    lines.extend(
        [
            "## Oyuncu Profili",
            "",
            "| Alan | Değer |",
            "| --- | --- |",
            f"| Nickname | {_fmt(profile.get('nickname'))} |",
            f"| Player ID | {_fmt(profile.get('player_id'))} |",
            f"| Ülke | {_fmt(profile.get('country'))} |",
            f"| CS2 Skill Level | {_fmt(profile.get('skill_level'))} |",
            f"| FACEIT ELO | {_fmt(profile.get('faceit_elo'))} |",
            f"| Steam / Oyun adı | {_fmt(profile.get('game_player_name'))} |",
            f"| Profil | {_fmt(profile.get('faceit_url'))} |",
            "",
        ]
    )

    if confidence:
        lines.extend(_render_data_confidence(confidence))

    lines.extend(
        [
            f"## Son {summary.get('total_matches', len(matches))} Maç — Performans Özeti",
            "",
            "| Metrik | Değer |",
            "| --- | --- |",
            f"| İstatistikli maç sayısı | {_fmt(summary.get('matches_with_stats'))} / {_fmt(summary.get('total_matches'))} |",
            f"| Galibiyet | {_fmt(summary.get('wins'))} |",
            f"| Mağlubiyet | {_fmt(summary.get('losses'))} |",
            f"| Kazanma oranı (%) | {_fmt(summary.get('win_rate_pct'))} |",
            f"| Ort. Kill | {_fmt(summary.get('avg_kills'))} |",
            f"| Ort. Death | {_fmt(summary.get('avg_deaths'))} |",
            f"| Ort. Assist | {_fmt(summary.get('avg_assists'))} |",
            f"| Ort. K/D | {_fmt(summary.get('avg_kd_ratio'))} |",
            f"| Ort. K/R | {_fmt(summary.get('avg_kr_ratio'))} |",
            f"| Ort. ADR | {_fmt(summary.get('avg_adr'))} |",
            f"| Ort. Headshot % | {_fmt(summary.get('avg_headshot_pct'))} |",
            f"| Ort. KAST | {_fmt(summary.get('avg_kast'))} |",
            f"| Toplam MVP | {_fmt(summary.get('total_mvps'))} |",
            f"| Toplam 3K | {_fmt(summary.get('total_triple_kills'))} |",
            f"| Toplam 4K | {_fmt(summary.get('total_quadro_kills'))} |",
            f"| Toplam ACE (5K) | {_fmt(summary.get('total_penta_kills'))} |",
            f"| En iyi K/D maçı | {_fmt(summary.get('best_kd_match_id'))} ({_fmt(summary.get('best_kd_value'))}) |",
            f"| En düşük K/D maçı | {_fmt(summary.get('worst_kd_match_id'))} ({_fmt(summary.get('worst_kd_value'))}) |",
            "",
            "## Son 5 Maç Formu",
            "",
            "| Metrik | Değer |",
            "| --- | --- |",
            f"| Skor | {_fmt(form.get('record'))} |",
            f"| Kazanma oranı (%) | {_fmt(form.get('win_rate_pct'))} |",
            f"| Ort. K/D | {_fmt(form.get('avg_kd_ratio'))} |",
            f"| Ort. ADR | {_fmt(form.get('avg_adr'))} |",
            f"| Form dizisi (yeniden → eski) | {_fmt(form.get('streak'))} |",
            f"| Streak yorumu | {_fmt(form.get('streak_comment'))} |",
            f"| En iyi maç | {_fmt(form.get('best_match'))} |",
            f"| En kötü maç | {_fmt(form.get('worst_match'))} |",
            f"| En riskli harita | {_fmt(form.get('riskiest_map'))} |",
            "",
            "| # | Sonuç | Harita | K/D | ADR | Tarih |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )

    for index, fm in enumerate(form.get("matches") or [], start=1):
        lines.append(
            f"| {index} | {_result_label(fm.get('won'))} | {_fmt(fm.get('map'))} | "
            f"{_fmt(fm.get('kd_ratio'))} | {_fmt(fm.get('adr'))} | {_fmt(fm.get('finished_at'))} |"
        )

    if not form.get("matches"):
        lines.append(f"| — | — | — | — | — | {MISSING_DATA_LABEL} |")

    map_note = map_stats.get("map_verdict_note")
    lines.extend(
        [
            "",
            "## Harita Bazlı Performans",
            "",
        ]
    )
    if map_note and map_note != MISSING_DATA_LABEL:
        lines.append(f"*{map_note}*")
        lines.append("")
    else:
        lines.extend(
            [
                f"**En iyi harita:** {_fmt(map_stats.get('best_map'))}  ",
                f"**En zayıf harita:** {_fmt(map_stats.get('worst_map'))}",
                "",
            ]
        )

    lines.extend(
        [
            "| Harita | Oynanan | Galibiyet | Mağlubiyet | Kazanma % |",
            "| --- | --- | --- | --- | --- |",
        ]
    )

    map_rows = map_stats.get("maps") or []
    if map_rows:
        for row in map_rows:
            lines.append(
                f"| {_fmt(row.get('map'))} | {_fmt(row.get('played'))} | "
                f"{_fmt(row.get('wins'))} | {_fmt(row.get('losses'))} | "
                f"{_fmt(row.get('win_rate_pct'))} |"
            )
    else:
        lines.append(f"| {MISSING_DATA_LABEL} | — | — | — | — |")

    lines.append("")
    lines.extend(_render_coaching_section(coaching))

    lines.extend(
        [
            "## Maç Detayları",
            "",
            "| Sonuç | Tarih | Harita | Rekabet | K | D | A | K/D | ADR | HS% | MVP |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for match in matches:
        if not match.get("stats_available"):
            lines.append(
                f"| {_result_label(match.get('won'))} | {_fmt(match.get('finished_at'))} | "
                f"{_fmt(match.get('map'))} | {_fmt(match.get('competition_name'))} | "
                f"{MISSING_DATA_LABEL} | {MISSING_DATA_LABEL} | {MISSING_DATA_LABEL} | "
                f"{MISSING_DATA_LABEL} | {MISSING_DATA_LABEL} | {MISSING_DATA_LABEL} | {MISSING_DATA_LABEL} |"
            )
            continue

        lines.append(
            f"| {_result_label(match.get('won'))} | {_fmt(match.get('finished_at'))} | "
            f"{_fmt(match.get('map'))} | {_fmt(match.get('competition_name'))} | "
            f"{_fmt(match.get('kills'))} | {_fmt(match.get('deaths'))} | {_fmt(match.get('assists'))} | "
            f"{_fmt(match.get('kd_ratio'))} | {_fmt(match.get('adr'))} | "
            f"{_fmt(match.get('headshot_pct'))} | {_fmt(match.get('mvps'))} |"
        )

    if missing_fields:
        lines.extend(["", "## Veri Eksik Alanlar", ""])
        for field in missing_fields:
            lines.append(f"- {field}")

    if errors:
        lines.extend(["", "## API / Toplama Uyarıları", ""])
        for err in errors:
            lines.append(f"- {err}")

    lines.extend(
        [
            "",
            "---",
            "",
            "*Bu rapor FACEIT Data API v4 verileriyle otomatik üretilmiştir. "
            "Eksik alanlar \"veri eksik\" olarak işaretlenmiştir.*",
            "",
        ]
    )

    return "\n".join(lines)
