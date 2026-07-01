from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import AI_EXPORTS_DIR, MISSING_DATA_LABEL


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return MISSING_DATA_LABEL
    return str(value)


def _pct(value: Any) -> str:
    if value is None or value == "":
        return MISSING_DATA_LABEL
    if isinstance(value, (int, float)):
        return f"{value}%"
    return str(value)


def _try_copy_clipboard(text: str) -> bool:
    try:
        import pyperclip

        pyperclip.copy(text)
        return True
    except Exception:
        return False


def _map_commentary(map_stats: dict[str, Any]) -> str:
    best = map_stats.get("best_map")
    worst = map_stats.get("worst_map")
    low = map_stats.get("low_sample_maps") or []
    parts: list[str] = []
    if best and best != MISSING_DATA_LABEL:
        parts.append(f"Güçlü pick: {best}.")
    if worst and worst != MISSING_DATA_LABEL:
        parts.append(f"Min 10 maçta zayıf: {worst} — demo/setup incelemesi önerilir.")
    if low:
        names = ", ".join(
            f"{r.get('map')} ({r.get('played')} maç)"
            for r in low[:4]
        )
        parts.append(f"Düşük örneklem: {names}.")
    return " ".join(parts) if parts else "Harita verisi sınırlı."


def _rifle_commentary(mech: dict[str, Any]) -> str:
    notes = mech.get("rifle_commentary") or mech.get("counter_strafe_commentary") or []
    if notes:
        return " ".join(notes)
    if not mech.get("rifle_reliable"):
        return "Rifle velocity verisi yetersiz."
    return "Belirgin rifle sinyali yok."


def _ak_m4_commentary(ak: dict[str, Any], m4: dict[str, Any]) -> tuple[str, str]:
    ak_note = "Veri yok."
    m4_note = "Veri yok."
    ak_first = ak.get("first_bullet_moving_pct")
    if isinstance(ak_first, (int, float)) and ak_first >= 40:
        ak_note = "İlk mermi çok sık hareket halinde — counter-strafe timing."
    elif ak.get("total_shots"):
        ak_note = "Belirgin AK sorunu tespit edilmedi."
    m4_long = m4.get("long_spray_pct")
    if isinstance(m4_long, (int, float)) and m4_long >= 35:
        m4_note = "Uzun spray / reset eksikliği."
    elif m4.get("total_shots"):
        m4_note = "Belirgin M4 sorunu tespit edilmedi."
    return ak_note, m4_note


def _pistol_commentary(mech: dict[str, Any]) -> tuple[str, str]:
    starter_first = mech.get("starter_pistol_first_bullet_moving_pct")
    force_mov = mech.get("force_pistol_shots_while_moving_pct")
    stability = "Veri yok."
    force_tol = "Veri yok."
    if isinstance(starter_first, (int, float)):
        stability = "Zayıf" if starter_first > 50 else "Kabul edilebilir"
    if isinstance(force_mov, (int, float)):
        force_tol = (
            "Yüksek hareket normal olabilir (Tec-9/Five-Seven); rifle disipliniyle karıştırma."
            if force_mov > 50
            else "Orta seviye."
        )
    return stability, force_tol


def _smg_commentary(mech: dict[str, Any]) -> str:
    notes = mech.get("smg_commentary") or []
    if notes:
        return notes[0]
    if (mech.get("smg_total_shots") or 0) > 0:
        return "SMG ayrı değerlendirilir; rifle/pistol yorumuna karışmaz."
    return "SMG verisi yok."


def derive_top_problems(mech: dict[str, Any], map_stats: dict[str, Any]) -> list[str]:
    """Metriklere göre en net 3 problem."""
    problems: list[str] = []
    ak = mech.get("ak_metrics") or {}
    m4 = mech.get("m4_metrics") or {}

    ak_first = ak.get("first_bullet_moving_pct")
    if isinstance(ak_first, (int, float)) and ak_first >= 40:
        problems.append("AK'da ilk mermi hareketli çıkıyor.")

    m4_long = m4.get("long_spray_pct")
    if isinstance(m4_long, (int, float)) and m4_long >= 35:
        problems.append("M4'te spray fazla uzuyor.")

    starter_mov = mech.get("starter_pistol_shots_while_moving_pct")
    starter_first = mech.get("starter_pistol_first_bullet_moving_pct")
    if isinstance(starter_first, (int, float)) and starter_first > 50:
        problems.append("Starter pistolde ilk mermi stabilitesi zayıf.")
    elif isinstance(starter_mov, (int, float)) and starter_mov > 35:
        problems.append("Starter pistolde ADAD sırasında erken click var.")

    rifle_mov = mech.get("rifle_shots_while_moving_pct")
    if len(problems) < 3 and isinstance(rifle_mov, (int, float)) and rifle_mov >= 50:
        problems.append("Rifle'da hareket halinde ateş oranı yüksek.")

    rifle_long = mech.get("rifle_long_spray_pct")
    if len(problems) < 3 and isinstance(rifle_long, (int, float)) and rifle_long >= 40:
        problems.append("Rifle'da uzun spray alışkanlığı var.")

    worst = map_stats.get("worst_map")
    if len(problems) < 3 and worst and worst != MISSING_DATA_LABEL:
        problems.append(f"{worst} haritasında performans zayıf (min 10 maç).")

    if not problems:
        problems.append("Belirgin mekanik problem tespit edilmedi; tutarlılık koru.")
    return problems[:3]


def derive_work_orders(mech: dict[str, Any], problems: list[str]) -> list[str]:
    """Bugünkü 3 maddelik çalışma emri."""
    orders: list[str] = []
    ak = mech.get("ak_metrics") or {}
    m4 = mech.get("m4_metrics") or {}
    starter_first = mech.get("starter_pistol_first_bullet_moving_pct")

    if isinstance(ak.get("first_bullet_moving_pct"), (int, float)) and ak["first_bullet_moving_pct"] >= 40:
        orders.append("5 dk AK counter-strafe + tek mermi.")
    else:
        orders.append("5 dk AK counter-strafe + 1–3 bullet tap.")

    if isinstance(m4.get("long_spray_pct"), (int, float)) and m4["long_spray_pct"] >= 35:
        orders.append("5 dk M4 5 mermi burst + reset.")
    else:
        orders.append("5 dk M4 spray kontrol drill.")

    if isinstance(starter_first, (int, float)) and starter_first > 50:
        orders.append("5 dk USP/Glock A-D dur tek mermi.")
    elif any("pistol" in p.lower() for p in problems):
        orders.append("5 dk pistol round ADAD + dur-ateş.")
    else:
        orders.append("5 dk utility + pozisyon review.")

    return orders[:3]


def render_tara_markdown(
    nickname: str,
    processed_payload: dict[str, Any],
    *,
    demo_note: str | None = None,
) -> str:
    """ChatGPT'ye yapıştırmalık kısa tara raporu."""
    profile = processed_payload.get("profile") or {}
    summary = processed_payload.get("summary") or {}
    form5 = processed_payload.get("recent_form") or {}
    map_stats = processed_payload.get("map_stats") or {}
    mechanics_lab = processed_payload.get("mechanics_lab") or {}
    agg = mechanics_lab.get("aggregated") or {}
    mech = agg.get("mechanics") or {}
    ak = mech.get("ak_metrics") or {}
    m4 = mech.get("m4_metrics") or {}

    from src.metrics import compute_recent_form

    form10 = compute_recent_form(
        {"matches": processed_payload.get("matches") or []},
        count=10,
    )

    low_sample = map_stats.get("low_sample_maps") or []
    low_lines = (
        ", ".join(f"{r.get('map')} ({r.get('played')} maç, WR {r.get('win_rate_pct')}%)" for r in low_sample)
        if low_sample
        else "Yok"
    )

    ak_note, m4_note = _ak_m4_commentary(ak, m4)
    pistol_stab, force_tol = _pistol_commentary(mech)
    problems = derive_top_problems(mech, map_stats)
    work_orders = derive_work_orders(mech, problems)

    deagle_shots = mech.get("deagle_total_shots", 0) or 0
    deagle_first = (
        _fmt(mech.get("deagle_first_bullet_moving_pct"))
        if deagle_shots > 0
        else "bu demoda Deagle verisi yok"
    )

    lines = [
        f"# {nickname} CS2 Tara Raporu",
        "",
        "## 1. Genel FACEIT Özeti",
        f"- Level: {_fmt(profile.get('skill_level'))}",
        f"- ELO: {_fmt(profile.get('faceit_elo'))}",
        f"- Son 90 gün maç: {_fmt(summary.get('total_matches'))}",
        f"- Winrate: {_pct(summary.get('win_rate_pct'))}",
        f"- K/D: {_fmt(summary.get('avg_kd_ratio'))}",
        f"- ADR: {_fmt(summary.get('avg_adr'))}",
        f"- HS%: {_pct(summary.get('avg_headshot_pct'))}",
        f"- Son 5 maç: {_fmt(form5.get('record'))} (K/D {_fmt(form5.get('avg_kd_ratio'))})",
        f"- Son 10 maç: {_fmt(form10.get('record'))} (K/D {_fmt(form10.get('avg_kd_ratio'))})",
        "",
    ]
    if demo_note:
        lines.extend([f"_{demo_note}_", ""])

    lines.extend([
        "## 2. Harita Özeti",
        f"- En güçlü harita: {_fmt(map_stats.get('best_map'))}",
        f"- Min 10 maçla en zayıf harita: {_fmt(map_stats.get('worst_map'))}",
        f"- Düşük örneklem haritalar: {low_lines}",
        f"- Kısa yorum: {_map_commentary(map_stats)}",
        "",
        "## 3. Rifle Mechanics",
    ])

    if mech.get("rifle_reliable") or mech.get("rifle_total_shots"):
        lines.extend([
            f"- rifle_total_shots: {_fmt(mech.get('rifle_total_shots'))}",
            f"- rifle_first_bullet_moving_pct: {_pct(mech.get('rifle_first_bullet_moving_pct'))}",
            f"- rifle_shots_while_moving_pct: {_pct(mech.get('rifle_shots_while_moving_pct'))}",
            f"- rifle_average_speed_at_shot: {_fmt(mech.get('rifle_average_speed_at_shot'))}",
            f"- rifle_median_speed_at_shot: {_fmt(mech.get('rifle_median_speed_at_shot'))}",
            f"- rifle_spray_length_average: {_fmt(mech.get('rifle_spray_length_average'))}",
            f"- rifle_long_spray_pct: {_pct(mech.get('rifle_long_spray_pct'))}",
            f"- Kısa yorum: {_rifle_commentary(mech)}",
        ])
    else:
        lines.append("- veri yok")
    lines.append("")

    lines.extend([
        "## 4. AK vs M4",
        "AK:",
        f"- total shots: {_fmt(ak.get('total_shots'))}",
        f"- first bullet moving: {_pct(ak.get('first_bullet_moving_pct'))}",
        f"- moving shots: {_pct(ak.get('shots_while_moving_pct'))}",
        f"- spray avg: {_fmt(ak.get('spray_length_average'))}",
        f"- long spray: {_pct(ak.get('long_spray_pct'))}",
        "",
        "M4/M4A1-S:",
        f"- total shots: {_fmt(m4.get('total_shots'))}",
        f"- first bullet moving: {_pct(m4.get('first_bullet_moving_pct'))}",
        f"- moving shots: {_pct(m4.get('shots_while_moving_pct'))}",
        f"- spray avg: {_fmt(m4.get('spray_length_average'))}",
        f"- long spray: {_pct(m4.get('long_spray_pct'))}",
        "",
        "Kısa yorum:",
        f"- AK'da ana sorun ne? {ak_note}",
        f"- M4'te ana sorun ne? {m4_note}",
        "",
        "## 5. Pistol Mechanics",
    ])

    if mech.get("pistol_total_shots") or mech.get("pistol_reliable"):
        lines.extend([
            f"- pistol_total_shots: {_fmt(mech.get('pistol_total_shots'))}",
            f"- pistol_first_bullet_moving_pct: {_pct(mech.get('pistol_first_bullet_moving_pct'))}",
            f"- pistol_shots_while_moving_pct: {_pct(mech.get('pistol_shots_while_moving_pct'))}",
            f"- pistol_spam_length_average: {_fmt(mech.get('pistol_spam_length_average'))}",
            f"- pistol_long_spam_pct: {_pct(mech.get('pistol_long_spam_pct'))}",
            "",
            "Starter pistol:",
            f"- total shots: {_fmt(mech.get('starter_pistol_total_shots'))}",
            f"- first bullet moving: {_pct(mech.get('starter_pistol_first_bullet_moving_pct'))}",
            f"- moving shots: {_pct(mech.get('starter_pistol_shots_while_moving_pct'))}",
            "",
            "Force pistol:",
            f"- total shots: {_fmt(mech.get('force_pistol_total_shots'))}",
            f"- first bullet moving: {_pct(mech.get('force_pistol_first_bullet_moving_pct'))}",
            f"- moving shots: {_pct(mech.get('force_pistol_shots_while_moving_pct'))}",
            "",
            "Deagle:",
            f"- total shots: {_fmt(deagle_shots) if deagle_shots else '0'}",
            f"- first bullet moving: {deagle_first}",
            "",
            "Kısa yorum:",
            f"- Pistol round ilk mermi stabilitesi iyi mi kötü mü? {pistol_stab}",
            f"- Force pistol hareketi toleranslı mı? {force_tol}",
        ])
    else:
        lines.append("- veri yok")
    lines.append("")

    lines.extend(["## 6. SMG Mechanics"])
    if mech.get("smg_total_shots") or mech.get("smg_reliable"):
        lines.extend([
            f"- smg_total_shots: {_fmt(mech.get('smg_total_shots'))}",
            f"- smg_first_bullet_moving_pct: {_pct(mech.get('smg_first_bullet_moving_pct'))}",
            f"- smg_shots_while_moving_pct: {_pct(mech.get('smg_shots_while_moving_pct'))}",
            f"- smg_long_spray_pct: {_pct(mech.get('smg_long_spray_pct'))}",
            f"- Kısa yorum: {_smg_commentary(mech)}",
        ])
    else:
        lines.append("- veri yok")
    lines.extend([
        "SMG verisi rifle/pistol yorumuna karıştırılmasın.",
        "",
        "## 7. Impact / Death Quality",
        "Impact / Death Quality metrikleri henüz eklenmedi.",
        "",
        "## 8. En Net 3 Problem",
    ])
    for i, p in enumerate(problems, 1):
        lines.append(f"{i}. {p}")
    lines.extend([
        "",
        "## 9. Bugünkü Çalışma Emri",
    ])
    for i, w in enumerate(work_orders, 1):
        lines.append(f"{i}. {w}")
    lines.extend([
        "",
        "## 10. ChatGPT'ye Sorulacak Soru",
        "",
        "Bu raporu koç gibi yorumla. En büyük 3 problemimi, bugün ne çalışmam gerektiğini ve Level 10 için en kritik düzeltmeyi söyle.",
        "",
    ])
    return "\n".join(lines)


def write_tara_export(
    nickname: str,
    processed_payload: dict[str, Any],
    export_dir: Path | None = None,
    *,
    demo_note: str | None = None,
) -> Path:
    """Tara raporunu dosyaya yazar."""
    export_dir = export_dir or AI_EXPORTS_DIR
    export_dir.mkdir(parents=True, exist_ok=True)
    safe = nickname.lower()
    path = export_dir / f"{safe}_tara_latest.md"
    content = render_tara_markdown(nickname, processed_payload, demo_note=demo_note)
    path.write_text(content, encoding="utf-8")
    return path


def copy_tara_to_clipboard(content: str) -> bool:
    return _try_copy_clipboard(content)
