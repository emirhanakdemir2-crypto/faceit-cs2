from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import MISSING_DATA_LABEL
from src.demo_parser import (
    build_mechanics_summary,
    demoparser_available,
    parse_demo_basic,
    prepare_demos_for_parsing,
    write_demo_debug_report,
)


def run_mechanics_lab(
    demo_folder: Path,
    nickname: str,
    *,
    max_demos: int = 20,
    debug_demo: bool = False,
    debug_report_dir: Path | None = None,
) -> dict[str, Any]:
    """Demo klasörünü tarar, sıkıştırılmış dosyaları çıkarır ve parse dener."""
    prep = prepare_demos_for_parsing(demo_folder)
    raw_files = prep.get("files") or []

    if not raw_files:
        return build_mechanics_summary([], [], demo_folder=demo_folder, nickname=nickname)

    parsed: list[dict[str, Any]] = []
    debug_paths: list[str] = []
    for entry in (prep.get("parseable") or [])[:max_demos]:
        result = parse_demo_basic(entry["path"], nickname, debug=debug_demo)
        result["source_compressed"] = entry.get("source_compressed")
        result["extraction"] = entry.get("extraction")
        parsed.append(result)
        if debug_demo and result.get("debug") and debug_report_dir is not None:
            safe = nickname.lower()
            stem = Path(entry.get("path", "demo")).stem
            per_path = debug_report_dir / f"{safe}_{stem}_demo_debug.md"
            latest_path = debug_report_dir / f"{safe}_demo_debug_latest.md"
            write_demo_debug_report(per_path, result["debug"])
            write_demo_debug_report(latest_path, result["debug"])
            debug_paths.append(str(per_path.resolve()))
            if str(latest_path.resolve()) not in debug_paths:
                debug_paths.append(str(latest_path.resolve()))

    summary = build_mechanics_summary(
        raw_files,
        parsed,
        demo_folder=demo_folder,
        nickname=nickname,
        extractions=prep.get("extractions") or [],
        preparation=prep,
    )
    if debug_paths:
        summary["debug_report_paths"] = debug_paths
    return summary


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
        "### Demo Başına Özet (Rifle-Only Counter-Strafe)",
        "",
        "| Demo | Eşleşme | K/D | Round | Total shots | Rifle shots | 1st bullet mov % | Mov % | Long spray % | Güven |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for card in lab.get("per_demo_cards") or aggregated.get("per_demo_cards") or []:
        kd = f"{card.get('kills', 0)}/{card.get('deaths', 0)}"
        lines.append(
            f"| `{_fmt(card.get('demo_file'))}` | {_yes_no(card.get('player_matched'))} | "
            f"{kd} | {_fmt(card.get('round_count'))} | {_fmt(card.get('total_shots'))} | "
            f"{_fmt(card.get('rifle_total_shots'))} | {_fmt(card.get('rifle_first_bullet_moving_pct'))} | "
            f"{_fmt(card.get('rifle_shots_while_moving_pct'))} | {_fmt(card.get('rifle_long_spray_pct'))} | "
            f"{_fmt(card.get('confidence'))} |"
        )
    lines.extend([
        "",
        "### Temel Demo Eventleri (Combined)",
        "",
        f"* Kill/death event çıktı mı: {_yes_no((agg.get('kills') or 0) + (agg.get('deaths') or 0) > 0)}",
        f"* Kill: {_fmt(agg.get('kills'))}",
        f"* Death: {_fmt(agg.get('deaths'))}",
        f"* Silahlar: {_fmt(', '.join(agg.get('weapons') or []) or MISSING_DATA_LABEL)}",
        f"* Round sayısı (max): {_fmt(agg.get('round_count'))}",
        f"* Shot event sayısı: {_fmt(agg.get('shot_count'))}",
        f"* Player tick sayısı: {_fmt(agg.get('tick_count'))}",
        f"* Shot event çıktı mı: {_yes_no(agg.get('shot_event_available'))}",
        f"* Tick/velocity verisi çıktı mı: {_yes_no(agg.get('tick_data_available'))}",
        f"* Velocity alanları bulundu mu: {_yes_no(agg.get('velocity_fields_found'))}",
        f"* Eşleşen shot+velocity sayısı: {_fmt(agg.get('shots_with_velocity'))}",
        "",
        f"* Mekanik metrik üretildi mi: {_yes_no(lab.get('mechanics_produced'))}",
        f"* Rifle metrik güven seviyesi: {_fmt(mech.get('rifle_metrics_confidence', mech.get('metrics_confidence', lab.get('confidence'))))}",
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

    lines.extend(["### Rifle-Only Counter-strafe / Spray (Combined)", ""])
    rifle_reliable = mech.get("rifle_reliable") or mech.get("reliable")
    if rifle_reliable:
        lines.extend([
            f"* rifle_total_shots: {_fmt(mech.get('rifle_total_shots'))}",
            f"* rifle_shots_with_velocity: {_fmt(mech.get('rifle_shots_with_velocity'))}",
            f"* rifle_shots_while_moving_pct (>34): {_fmt(mech.get('rifle_shots_while_moving_pct'))}",
            f"* rifle_first_bullet_moving_pct: {_fmt(mech.get('rifle_first_bullet_moving_pct'))}",
            f"* rifle_average_speed_at_shot: {_fmt(mech.get('rifle_average_speed_at_shot'))}",
            f"* rifle_median_speed_at_shot: {_fmt(mech.get('rifle_median_speed_at_shot'))}",
            f"* rifle_spray_length_average: {_fmt(mech.get('rifle_spray_length_average'))}",
            f"* rifle_long_spray_pct (7+ mermi): {_fmt(mech.get('rifle_long_spray_pct'))}",
            "",
        ])
        ak = mech.get("ak_metrics") or {}
        m4 = mech.get("m4_metrics") or {}
        if ak.get("reliable") or ak.get("total_shots"):
            lines.extend([
                "**AK (combined):**",
                f"* total_shots: {_fmt(ak.get('total_shots'))}",
                f"* first_bullet_moving_pct: {_fmt(ak.get('first_bullet_moving_pct'))}",
                f"* shots_while_moving_pct: {_fmt(ak.get('shots_while_moving_pct'))}",
                f"* spray_length_average: {_fmt(ak.get('spray_length_average'))}",
                f"* long_spray_pct: {_fmt(ak.get('long_spray_pct'))}",
                "",
            ])
        if m4.get("reliable") or m4.get("total_shots"):
            lines.extend([
                "**M4 / M4A1-S (combined):**",
                f"* total_shots: {_fmt(m4.get('total_shots'))}",
                f"* first_bullet_moving_pct: {_fmt(m4.get('first_bullet_moving_pct'))}",
                f"* shots_while_moving_pct: {_fmt(m4.get('shots_while_moving_pct'))}",
                f"* spray_length_average: {_fmt(m4.get('spray_length_average'))}",
                f"* long_spray_pct: {_fmt(m4.get('long_spray_pct'))}",
                "",
            ])
        commentary = mech.get("counter_strafe_commentary") or mech.get("commentary") or []
        if commentary:
            lines.extend(["**Counter-strafe yorumu (rifle-only):**", ""])
            for note in commentary:
                lines.append(f"- {note}")
            lines.append("")
        if mech.get("note"):
            lines.append(f"_{mech['note']}_")
            lines.append("")
        lines.extend([
            "### Genel silah metrikleri (SMG/pistol dahil — counter-strafe için kullanılmaz)",
            "",
            f"* Total shots: {_fmt(mech.get('total_shots'))}",
            f"* Shots while moving %: {_fmt(mech.get('shots_while_moving_pct'))}",
            f"* First bullet moving %: {_fmt(mech.get('first_bullet_moving_pct'))}",
            f"* Spray length average: {_fmt(mech.get('spray_length_average'))}",
            f"* Long spray %: {_fmt(mech.get('long_spray_pct'))}",
            "",
        ])
    else:
        note = mech.get(
            "note",
            "Rifle shot event var ama user_velocity alanı bulunamadı veya eşleşmedi.",
        )
        lines.append(f"_{note}_")
        lines.append("")

    lines.extend(["### Counter-strafe / Spray Ön Metrikleri (legacy genel)", ""])
    if mech.get("reliable"):
        lines.extend([
            f"* Total shots (gun): {_fmt(mech.get('total_shots'))}",
            f"* Shots with velocity: {_fmt(mech.get('shots_with_velocity'))}",
            f"* Burst count: {_fmt(mech.get('burst_count'))}",
            f"* Average speed at shot: {_fmt(mech.get('average_speed_at_shot'))}",
            f"* Median speed at shot: {_fmt(mech.get('median_speed_at_shot'))}",
            f"* Shots while moving % (>34): {_fmt(mech.get('shots_while_moving_pct'))}",
            f"* First bullet moving %: {_fmt(mech.get('first_bullet_moving_pct'))}",
            f"* Spray length average: {_fmt(mech.get('spray_length_average'))}",
            f"* Long spray % (7+ mermi): {_fmt(mech.get('long_spray_pct'))}",
            f"* AK/M4 burst average: {_fmt(mech.get('ak_m4_burst_average'))}",
            "",
            "**Weapon shot counts:**",
            "",
        ])
        for weapon, count in sorted(
            (mech.get("weapon_shot_counts") or {}).items(),
            key=lambda x: -x[1],
        )[:12]:
            lines.append(f"- {weapon}: {count}")
        ak_m4 = mech.get("ak_m4_shot_counts") or {}
        if ak_m4:
            lines.extend(["", "**AK/M4 shot counts:**", ""])
            for weapon, count in sorted(ak_m4.items(), key=lambda x: -x[1]):
                lines.append(f"- {weapon}: {count}")
        lines.append("")
        commentary = mech.get("commentary") or []
        if commentary:
            lines.extend(["**Yorum:**", ""])
            for note in commentary:
                lines.append(f"- {note}")
            lines.append("")
        if mech.get("note"):
            lines.append(f"_{mech['note']}_")
            lines.append("")
    else:
        note = mech.get(
            "note",
            "Shot event var ama player velocity alanı bulunamadı veya eşleşmedi.",
        )
        lines.append(f"_{note}_")
        lines.append("")

    if lab.get("debug_report_paths"):
        lines.extend([
            "### Debug Raporu",
            "",
        ])
        for p in lab["debug_report_paths"]:
            lines.append(f"- `{p}`")
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
