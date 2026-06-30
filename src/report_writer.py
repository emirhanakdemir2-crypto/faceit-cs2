from __future__ import annotations

from pathlib import Path
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


GEMINI_UNAVAILABLE_LABEL = "Gemini AI yorumu alınamadı"


def _summary_table(summary: dict[str, Any], title: str) -> list[str]:
    lines = [f"### {title}", "", "| Metrik | Değer |", "| --- | --- |"]
    rows = [
        ("Maç sayısı", summary.get("total_matches")),
        ("İstatistikli maç", summary.get("matches_with_stats")),
        ("Galibiyet", summary.get("wins")),
        ("Mağlubiyet", summary.get("losses")),
        ("Kazanma %", summary.get("win_rate_pct")),
        ("Ort. K/D", summary.get("avg_kd_ratio")),
        ("Ort. ADR", summary.get("avg_adr")),
        ("Ort. HS%", summary.get("avg_headshot_pct")),
        ("Ort. KAST", summary.get("avg_kast")),
    ]
    for label, val in rows:
        lines.append(f"| {label} | {_fmt(val)} |")
    lines.append("")
    return lines


def _render_session_coach_sections(session: dict[str, Any]) -> list[str]:
    baseline = session.get("baseline_summary") or {}
    baseline_maps = session.get("baseline_map_stats") or {}
    recent = session.get("recent_form") or {}
    comparison = session.get("comparison") or {}
    risk = session.get("focus_risk") or {}
    recent_count = session.get("recent_count", 10)
    days = session.get("days", 90)

    lines: list[str] = [
        "## Session Coach — Son Maç Gelişim Takibi",
        "",
        f"_90 gün baseline vs son {recent_count} maç formu._",
        "",
        f"## {days} Günlük Baseline",
        "",
        "| Metrik | Değer |",
        "| --- | --- |",
        f"| Win rate | {_fmt(baseline.get('win_rate_pct'))}% |",
        f"| K/D | {_fmt(baseline.get('avg_kd_ratio'))} |",
        f"| ADR | {_fmt(baseline.get('avg_adr'))} |",
        f"| HS% | {_fmt(baseline.get('avg_headshot_pct'))} |",
        "",
        f"**Güçlü harita:** {_fmt(baseline_maps.get('best_map'))}  ",
        f"**Zayıf harita:** {_fmt(baseline_maps.get('worst_map'))}",
        "",
        "| Harita | Oynanan | G | M | Kazanma % |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in baseline_maps.get("maps") or []:
        lines.append(
            f"| {_fmt(row.get('map'))} | {_fmt(row.get('played'))} | "
            f"{_fmt(row.get('wins'))} | {_fmt(row.get('losses'))} | "
            f"{_fmt(row.get('win_rate_pct'))} |"
        )
    lines.append("")

    lines.extend([
        f"## Son {recent_count} Maç Formu",
        "",
        f"| Metrik | Değer |",
        "| --- | --- |",
        f"| Win rate | {_fmt(recent.get('win_rate_pct'))}% |",
        f"| K/D | {_fmt(recent.get('avg_kd_ratio'))} |",
        f"| ADR | {_fmt(recent.get('avg_adr'))} |",
        f"| HS% | {_fmt(recent.get('avg_headshot_pct'))} |",
        f"| Skor | {_fmt(recent.get('record'))} |",
        f"| Win streak | {_fmt(recent.get('current_win_streak'))} |",
        f"| Loss streak | {_fmt(recent.get('current_loss_streak'))} |",
        f"| En iyi maç | {_fmt(recent.get('best_match'))} |",
        f"| En kötü maç | {_fmt(recent.get('worst_match'))} |",
        "",
        "**Harita dağılımı:**",
        "",
    ])
    for row in recent.get("map_distribution") or []:
        lines.append(f"- {_fmt(row.get('map'))}: {row.get('played')} maç")
    lines.append("")

    high_adr = recent.get("high_adr_losses") or []
    if high_adr:
        lines.append("**Yüksek ADR + loss maçları:**")
        lines.append("")
        for item in high_adr:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend([
        "## Baseline'a Göre Değişim",
        "",
        "| Metrik | 90g Baseline | Son form | Fark |",
        "| --- | --- | --- | --- |",
    ])
    for row in comparison.get("comparisons") or []:
        delta = row.get("delta")
        delta_str = f"+{delta}" if isinstance(delta, (int, float)) and delta > 0 else _fmt(delta)
        lines.append(
            f"| {row.get('metric')} | {_fmt(row.get('baseline'))} | "
            f"{_fmt(row.get('recent'))} | {delta_str} |"
        )
    lines.append("")
    for mc in comparison.get("map_comparisons") or []:
        lines.append(f"- {mc}")
    if comparison.get("map_comparisons"):
        lines.append("")
    lines.append("**Yorum:**")
    lines.append("")
    for note in comparison.get("commentary") or []:
        lines.append(f"- {note}")
    lines.append("")

    lines.extend([
        "## Focus Risk Score",
        "",
        f"**Skor: {risk.get('score', 0)}/100** — {_fmt(risk.get('band'))}",
        "",
        "**Risk faktörleri:**",
        "",
    ])
    for factor in risk.get("factors") or []:
        lines.append(f"- {factor}")
    lines.append("")
    lines.extend([
        "## Bugünkü Queue Kararı",
        "",
        f"**{_fmt(risk.get('queue_decision'))}**",
        "",
        "## Sonraki Maç İçin Tek Odak",
        "",
        f"**{_fmt(session.get('next_match_focus'))}**",
        "",
        "## Mental / Toxicity Notları",
        "",
    ])
    for note in session.get("mental_notes") or []:
        if note.startswith("- "):
            lines.append(note)
        else:
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
    period_comparison: dict[str, Any] | None = None,
    period_insights: list[str] | None = None,
    persistent_problems: list[str] | None = None,
    new_matches_baseline: dict[str, Any] | None = None,
    demo_analysis: dict[str, Any] | None = None,
    ai_enabled: bool = False,
    ai_comment: str | None = None,
    ai_export_path: str | None = None,
    session_coach: dict[str, Any] | None = None,
    session_only: bool = False,
) -> str:
    profile = normalized.get("profile") or {}
    matches = normalized.get("matches") or []
    nickname = normalized.get("nickname") or profile.get("nickname") or "oyuncu"
    errors = normalized.get("collection_errors") or []
    window = normalized.get("analysis_window") or {}
    days = window.get("days", 90)

    form = form or {}
    map_stats = map_stats or {"maps": [], "best_map": MISSING_DATA_LABEL, "worst_map": MISSING_DATA_LABEL}
    memory = memory or {}
    confidence = confidence or {}
    period_comparison = period_comparison or {}
    period_insights = period_insights or []
    persistent_problems = persistent_problems or []
    new_matches_baseline = new_matches_baseline or {}
    demo_analysis = demo_analysis or {}
    missing_fields = missing_fields or []

    title = (
        f"# Session Coach — {_fmt(nickname)}"
        if session_only
        else f"# FACEIT CS2 Gelişim Raporu — {_fmt(nickname)}"
    )
    lines: list[str] = [
        title,
        "",
        f"*Oluşturulma: {normalized.get('generated_at', MISSING_DATA_LABEL)}*",
        f"*Analiz penceresi: son {days} gün / {summary.get('total_matches', len(matches))} maç*",
        "",
        "## Oyuncu Profili",
        "",
        "| Alan | Değer |",
        "| --- | --- |",
        f"| Nickname | {_fmt(profile.get('nickname'))} |",
        f"| Player ID | {_fmt(profile.get('player_id'))} |",
        f"| CS2 Skill Level | {_fmt(profile.get('skill_level'))} |",
        f"| FACEIT ELO | {_fmt(profile.get('faceit_elo'))} |",
        f"| Profil | {_fmt(profile.get('faceit_url'))} |",
        "",
    ]

    if session_coach:
        lines.extend(_render_session_coach_sections(session_coach))

    if session_only:
        lines.extend([
            "---",
            "",
            "*Session Coach — faceit-cs2-coach*",
            "",
        ])
        return "\n".join(lines)

    lines.extend([
        "## Veri Güveni",
        "",
        f"**Seviye: {_fmt(confidence.get('level'))}** — {_fmt(confidence.get('detail'))}",
        "",
    ])
    for note in confidence.get("notes") or []:
        lines.append(f"- {note}")
    lines.append("")

    lines.extend(_summary_table(summary, f"{days} Günlük Genel Özet"))

    lines.extend(["## Dönem Kıyaslaması (İlk 30 / Orta 30 / Son 30 Gün)", ""])
    for key in ("first_30_days", "middle_30_days", "last_30_days"):
        block = period_comparison.get(key) or {}
        lines.extend(_summary_table(block.get("summary", {}), block.get("label", key)))
    if period_insights:
        lines.append("**Dönem trendleri:**")
        lines.append("")
        for ins in period_insights:
            lines.append(f"- {ins}")
        lines.append("")

    lines.extend(["## Önceki Analizden Bu Yana Gelişim / Gerileme", ""])
    lines.append(f"**{_fmt(memory.get('status_message'))}**")
    lines.append("")
    if new_matches_baseline.get("has_new"):
        lines.append(f"_{_fmt(new_matches_baseline.get('message'))}_")
        lines.append("")
        for ins in new_matches_baseline.get("insights") or []:
            lines.append(f"- {ins}")
        lines.append("")
    lines.append("### Gelişen Alanlar")
    lines.append("")
    for item in memory.get("improved_areas") or ["—"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Kötüleşen Alanlar")
    lines.append("")
    for item in memory.get("worsened_areas") or ["—"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.extend(["## Harita Havuzu Analizi", ""])
    map_note = map_stats.get("map_verdict_note")
    if map_note and map_note != MISSING_DATA_LABEL:
        lines.append(f"*{map_note}*")
        lines.append("")
    else:
        lines.extend([
            f"**En iyi harita (min. 3 maç):** {_fmt(map_stats.get('best_map'))}  ",
            f"**En zayıf harita:** {_fmt(map_stats.get('worst_map'))}",
            "",
        ])
    lines.extend([
        "| Harita | Oynanan | G | M | Kazanma % |",
        "| --- | --- | --- | --- | --- |",
    ])
    for row in map_stats.get("maps") or []:
        lines.append(
            f"| {_fmt(row.get('map'))} | {_fmt(row.get('played'))} | "
            f"{_fmt(row.get('wins'))} | {_fmt(row.get('losses'))} | "
            f"{_fmt(row.get('win_rate_pct'))} |"
        )
    lines.append("")

    lines.extend([
        "## Kısa Vadeli Form — Son 5 Maç",
        "",
        "_Ana koçluk kararı bu bölüme değil, 90 günlük dönem özetine dayanır._",
        "",
        f"| Skor | {_fmt(form.get('record'))} |",
        f"| Ort. K/D | {_fmt(form.get('avg_kd_ratio'))} |",
        f"| Ort. ADR | {_fmt(form.get('avg_adr'))} |",
        f"| Streak | {_fmt(form.get('streak'))} |",
        f"| Streak yorumu | {_fmt(form.get('streak_comment'))} |",
        f"| En iyi maç | {_fmt(form.get('best_match'))} |",
        f"| En kötü maç | {_fmt(form.get('worst_match'))} |",
        f"| En riskli harita | {_fmt(form.get('riskiest_map'))} |",
        "",
    ])

    lines.extend(["## Kalıcı Problemler", ""])
    for p in persistent_problems:
        lines.append(f"- {p}")
    lines.append("")

    lines.extend(["## 7 Günlük Odak Planı", ""])
    lines.append("| Gün | Odak |")
    lines.append("| --- | --- |")
    for day in memory.get("focus_plan_7d") or []:
        lines.append(f"| {_fmt(day.get('day'))} | {_fmt(day.get('focus'))} |")
    lines.append("")

    lines.extend(["## Demo Mekanik Analizi", ""])
    if demo_analysis.get("found") is False:
        lines.append(f"_{_fmt(demo_analysis.get('message'))}_")
    else:
        lines.append(f"_{_fmt(demo_analysis.get('message', 'Demo klasörü taranmadı.'))}_")
        lines.append("")
        if demo_analysis.get("files"):
            lines.append("| Dosya | match_id | Boyut (MB) |")
            lines.append("| --- | --- | --- |")
            for f in demo_analysis.get("files") or []:
                lines.append(
                    f"| {_fmt(f.get('filename'))} | {_fmt(f.get('match_id'))} | {_fmt(f.get('size_mb'))} |"
                )
            lines.append("")
        mech = demo_analysis.get("mechanics") or {}
        if mech.get("note"):
            lines.append(f"*{mech['note']}*")
            lines.append("")

    lines.extend(["## Mekanik Analiz Hedef Metrikleri", ""])
    lines.append("_Counter-strafe ve spray FACEIT API'den alınamaz; demo gerekir._")
    lines.append("")
    lines.append("| Metrik | Değer | Kaynak |")
    lines.append("| --- | --- | --- |")
    mech = demo_analysis.get("mechanics") or {}
    for tm in demo_analysis.get("target_metrics") or []:
        key = tm.get("key", "")
        val = mech.get(key, tm.get("value", MISSING_DATA_LABEL))
        lines.append(f"| {tm.get('label')} | {_fmt(val)} | {tm.get('source')} |")
    lines.append("")

    lines.extend(["## AI Export Belgesi", ""])
    if ai_export_path:
        lines.append(f"AI export: `{ai_export_path}`")
        lines.append("")
        lines.append(
            "_ChatGPT/Gemini/Claude'a yapıştırmak için `--export-ai-prompt` ile oluşturulur._"
        )
    else:
        lines.append(
            "_AI export oluşturulmadı. `--export-ai-prompt` parametresiyle çalıştırın._"
        )
    lines.append("")

    lines.extend(["## Gemini AI Koçluk Yorumu", ""])
    if not ai_enabled:
        lines.append("_AI yorumu kapalı. Açmak için `--ai` parametresiyle çalıştırın._")
    elif ai_comment:
        lines.append(ai_comment)
    else:
        lines.append(GEMINI_UNAVAILABLE_LABEL)
    lines.append("")

    lines.extend([
        "## Maç Detayları (özet)",
        "",
        "| Sonuç | Tarih | Harita | K/D | ADR |",
        "| --- | --- | --- | --- | --- |",
    ])
    for match in matches[:30]:
        lines.append(
            f"| {_result_label(match.get('won'))} | {_fmt(match.get('finished_at'))} | "
            f"{_fmt(match.get('map'))} | {_fmt(match.get('kd_ratio'))} | {_fmt(match.get('adr'))} |"
        )
    if len(matches) > 30:
        lines.append(f"| ... | +{len(matches) - 30} maç daha | — | — | — |")
    lines.append("")

    if missing_fields:
        lines.extend(["## Veri Eksik Alanlar", ""])
        for field in missing_fields[:25]:
            lines.append(f"- {field}")
        if len(missing_fields) > 25:
            lines.append(f"- ... ve {len(missing_fields) - 25} alan daha")
        lines.append("")

    if errors:
        lines.extend(["## API Uyarıları", ""])
        for err in errors[:15]:
            lines.append(f"- {err}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "*FACEIT Data API v4 + hafızalı koçluk sistemi. Mekanik metrikler demo gerektirir.*",
        "",
    ])
    return "\n".join(lines)
