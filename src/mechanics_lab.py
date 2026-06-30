from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import MISSING_DATA_LABEL
from src.demo_parser import (
    build_mechanics_summary,
    demoparser_available,
    parse_demo_basic,
    prepare_demos_for_parsing,
)


def run_mechanics_lab(demo_folder: Path, nickname: str, *, max_demos: int = 5) -> dict[str, Any]:
    """Demo klasörünü tarar, sıkıştırılmış dosyaları çıkarır ve parse dener."""
    prep = prepare_demos_for_parsing(demo_folder)
    raw_files = prep.get("files") or []

    if not raw_files:
        return build_mechanics_summary([], [], demo_folder=demo_folder, nickname=nickname)

    parsed: list[dict[str, Any]] = []
    for entry in (prep.get("parseable") or [])[:max_demos]:
        result = parse_demo_basic(entry["path"], nickname)
        result["source_compressed"] = entry.get("source_compressed")
        result["extraction"] = entry.get("extraction")
        parsed.append(result)

    return build_mechanics_summary(
        raw_files,
        parsed,
        demo_folder=demo_folder,
        nickname=nickname,
        extractions=prep.get("extractions") or [],
        preparation=prep,
    )


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return MISSING_DATA_LABEL
    return str(value)


def _yes_no(flag: bool | None) -> str:
    if flag is True:
        return "Evet"
    if flag is False:
        return "Hayır"
    return MISSING_DATA_LABEL


def render_mechanics_lab_markdown(lab: dict[str, Any]) -> list[str]:
    """Mechanics Lab rapor bölümünü markdown satırları olarak döner."""
    agg = lab.get("aggregated") or {}
    mech = agg.get("mechanics") or {}
    lines: list[str] = [
        "## Mechanics Lab — Demo Analizi",
        "",
        "### Demo Durumu",
        "",
        f"* Demo klasörü: `{_fmt(lab.get('folder'))}`",
        f"* Bulunan demo sayısı: {_fmt(lab.get('found_count'))}",
        f"* Okunan demo sayısı: {_fmt(lab.get('parsed_count'))}",
        f"* Parser: {_fmt(lab.get('parser'))}",
        f"* Güven seviyesi: {_fmt(lab.get('confidence'))}",
        "",
        "### Sıkıştırma ve Çıkarma",
        "",
        f"* Sıkıştırılmış demo bulundu mu: {_yes_no(lab.get('compressed_found'))}",
    ]

    extractions = lab.get("extractions") or []
    if extractions:
        for ext in extractions:
            extracted = ext.get("extracted") and not ext.get("error")
            lines.extend([
                f"* Kaynak: `{_fmt(ext.get('source'))}`",
                f"* .dem olarak çıkarıldı mı: {_yes_no(extracted)}",
                f"* Çıkarılan dosya yolu: `{_fmt(ext.get('output_path'))}`",
            ])
            if ext.get("skipped_existing"):
                lines.append("* Not: .dem zaten vardı, tekrar çıkarılmadı.")
            if ext.get("error"):
                lines.append(f"* Çıkarma hatası: {_fmt(ext['error'])}")
    else:
        lines.append("* Sıkıştırılmış dosya yok veya çıkarma denenmedi.")

    lines.extend([
        "",
        "### Parser Denemesi",
        "",
        f"* Parser denendi mi: {_yes_no(lab.get('parser_attempted'))}",
        f"* Parser sonucu: {_fmt(lab.get('parser_result'))}",
        "",
    ])

    if lab.get("compressed_note"):
        lines.append(f"_{lab['compressed_note']}_")
        lines.append("")

    if lab.get("status") == "unavailable":
        lines.append(f"**Durum:** {_fmt(lab.get('reason', 'Demo yok veya okunamadı.'))}")
        lines.append("")
        lines.extend(_warning_block())
        return lines

    lines.extend([
        "### Oyuncu Eşleşmesi",
        "",
        f"* Nickname: {_fmt(lab.get('nickname'))}",
        f"* Demo içinde eşleşme: {_yes_no(lab.get('player_matched'))}",
        f"* Not: {_fmt(lab.get('matched_name') or 'Oyuncu adı demo içinde bulunamadı; metrikler sınırlı olabilir.')}",
        "",
        "### Temel Demo Eventleri",
        "",
        f"* Kill/death event çıktı mı: {_yes_no((agg.get('kills') or 0) + (agg.get('deaths') or 0) > 0)}",
        f"* Kill: {_fmt(agg.get('kills'))}",
        f"* Death: {_fmt(agg.get('deaths'))}",
        f"* Silahlar: {_fmt(', '.join(agg.get('weapons') or []) or MISSING_DATA_LABEL)}",
        f"* Round sayısı: {_fmt(agg.get('round_count'))}",
        f"* Shot event çıktı mı: {_yes_no(agg.get('shot_event_available'))}",
        f"* Tick/velocity verisi çıktı mı: {_yes_no(agg.get('tick_data_available'))}",
        "",
        f"* Mekanik metrik üretildi mi: {_yes_no(lab.get('mechanics_produced'))}",
        "",
    ])

    if lab.get("demos"):
        lines.extend(["**Demo dosyaları:**", ""])
        for demo in lab.get("demos") or []:
            status = demo.get("status", "?")
            fname = demo.get("demo_file", "?")
            src = demo.get("source_compressed")
            prefix = f"`{fname}`"
            if src:
                prefix += f" (kaynak: `{src}`)"
            if status == "ok":
                lines.append(
                    f"- {prefix} — kill {demo.get('kills', 0)}, death {demo.get('deaths', 0)}, "
                    f"shot {_yes_no(demo.get('shot_event_available'))}, "
                    f"tick {_yes_no(demo.get('tick_data_available'))}, "
                    f"confidence {_fmt(demo.get('confidence'))}"
                )
            else:
                lines.append(f"- {prefix} — {_fmt(demo.get('reason', 'okunamadı'))}")
        lines.append("")

    lines.extend(["### Counter-strafe / Spray Ön Metrikleri", ""])
    if mech.get("reliable"):
        lines.extend([
            f"* Shots while moving %: {_fmt(mech.get('shots_while_moving_pct'))}",
            f"* First bullet moving %: {_fmt(mech.get('first_bullet_moving_pct'))}",
            f"* Average speed at shot: {_fmt(mech.get('average_speed_at_shot'))}",
            f"* Spray length average: {_fmt(mech.get('spray_length_average'))}",
            "",
            "**Weapon shot counts:**",
            "",
        ])
        for weapon, count in sorted(
            (mech.get("weapon_shot_counts") or {}).items(),
            key=lambda x: -x[1],
        )[:12]:
            lines.append(f"- {weapon}: {count}")
        lines.append("")
        if mech.get("note"):
            lines.append(f"_{mech['note']}_")
            lines.append("")
    else:
        lines.append(f"_{mech.get('note', 'Bu demoda shot + velocity eşleşmesi güvenilir çıkarılamadı.')}_")
        lines.append("")

    lines.extend(_warning_block())
    return lines


def _warning_block() -> list[str]:
    return [
        "### Uyarı",
        "",
        "_Bu mekanik analiz ilk sürümdür. Kesin counter-strafe/spray teşhisi için daha fazla demo ve event doğrulaması gerekir._",
        "",
    ]
