from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import MISSING_DATA_LABEL
from src.demo_parser import (
    build_mechanics_summary,
    demoparser_available,
    find_demo_files,
    parse_demo_basic,
)


def run_mechanics_lab(demo_folder: Path, nickname: str, *, max_demos: int = 5) -> dict[str, Any]:
    """Demo klasörünü tarar ve opsiyonel parser ile mekanik özet üretir."""
    files = find_demo_files(demo_folder)
    if not files:
        return build_mechanics_summary([], [], demo_folder=demo_folder, nickname=nickname)

    parseable = [f for f in files if f.get("parseable")]
    parsed: list[dict[str, Any]] = []

    for entry in parseable[:max_demos]:
        parsed.append(parse_demo_basic(entry["path"], nickname))

    for entry in files:
        if entry.get("compressed"):
            parsed.append({
                "demo_file": entry["filename"],
                "demo_path": entry["path"],
                "parser": "demoparser2" if demoparser_available() else "none",
                "status": "unavailable",
                "reason": "Sıkıştırılmış demo bulundu; önce .dem olarak çıkarılmalı.",
                "demo_count": 0,
                "confidence": "none",
                "parser_status": "skipped",
            })

    return build_mechanics_summary(files, parsed, demo_folder=demo_folder, nickname=nickname)


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return MISSING_DATA_LABEL
    return str(value)


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
    ]

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
        f"* Demo içinde eşleşme: {'Evet' if lab.get('player_matched') else 'Hayır'}",
        f"* Not: {_fmt(lab.get('matched_name') or 'Oyuncu adı demo içinde bulunamadı; metrikler sınırlı olabilir.')}",
        "",
        "### Temel Demo Eventleri",
        "",
        f"* Kill: {_fmt(agg.get('kills'))}",
        f"* Death: {_fmt(agg.get('deaths'))}",
        f"* Silahlar: {_fmt(', '.join(agg.get('weapons') or []) or MISSING_DATA_LABEL)}",
        f"* Round sayısı: {_fmt(agg.get('round_count'))}",
        f"* Tick data: {'Evet' if agg.get('tick_data_available') else 'Hayır / veri yetersiz'}",
        f"* Shot event: {'Evet' if agg.get('shot_event_available') else 'Hayır / veri yetersiz'}",
        "",
    ])

    if lab.get("demos"):
        lines.extend(["**Demo dosyaları:**", ""])
        for demo in lab.get("demos") or []:
            status = demo.get("status", "?")
            fname = demo.get("demo_file", "?")
            if status == "ok":
                lines.append(
                    f"- `{fname}` — kill {demo.get('kills', 0)}, death {demo.get('deaths', 0)}, "
                    f"confidence {_fmt(demo.get('confidence'))}"
                )
            else:
                lines.append(f"- `{fname}` — {_fmt(demo.get('reason', 'okunamadı'))}")
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
