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
from src.impact_analyzer import write_impact_debug_report


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
    agg = summary.get("aggregated") or {}
    impact = agg.get("impact") or {}
    if debug_report_dir is not None and impact:
        safe = nickname.lower()
        impact_path = debug_report_dir / f"{safe}_impact_debug_latest.md"
        write_impact_debug_report(impact_path, impact, nickname)
        summary["impact_debug_report_path"] = str(impact_path.resolve())
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


def _bullet_list(notes: list[str]) -> list[str]:
    if not notes:
        return []
    lines = ["**Yorum:**", ""]
    for note in notes:
        lines.append(f"- {note}")
    lines.append("")
    return lines


def render_mechanics_lab_markdown(lab: dict[str, Any]) -> list[str]:
    """Mechanics Lab rapor bölümünü markdown satırları olarak döner."""
    agg = lab.get("aggregated") or {}
    mech = agg.get("mechanics") or {}
    lines: list[str] = [
        "## Mechanics Lab — Demo Analizi",
        "",
        "### Demo Status",
        "",
        f"* Demo klasörü: `{_fmt(lab.get('folder'))}`",
        f"* Parse edilen demo: {_fmt(lab.get('parsed_count'))} / {_fmt(lab.get('found_count'))}",
        f"* Parser: {_fmt(lab.get('parser'))}",
        f"* Oyuncu eşleşmesi: {_yes_no(lab.get('player_matched'))} ({_fmt(lab.get('matched_name'))})",
        f"* Parser sonucu: {_fmt(lab.get('parser_result'))}",
    ]

    extractions = lab.get("extractions") or []
    if extractions:
        for ext in extractions:
            extracted = ext.get("extracted") and not ext.get("error")
            lines.append(
                f"* `{_fmt(ext.get('source'))}` → .dem: {_yes_no(extracted)}"
            )
            if ext.get("error"):
                lines.append(f"  * Hata: {_fmt(ext['error'])}")
    elif lab.get("compressed_found"):
        lines.append("* Sıkıştırılmış demo: mevcut .dem dosyaları kullanıldı.")

    if lab.get("status") == "unavailable":
        lines.extend(["", f"**Durum:** {_fmt(lab.get('reason', 'Demo yok veya okunamadı.'))}", ""])
        lines.extend(_warning_block())
        return lines

    if lab.get("demos"):
        lines.extend(["", "**Demo dosyaları:**", ""])
        for demo in lab.get("demos") or []:
            fname = demo.get("demo_file", "?")
            src = demo.get("source_compressed")
            prefix = f"`{fname}`"
            if src:
                prefix += f" (kaynak: `{src}`)"
            if demo.get("status") == "ok":
                lines.append(
                    f"- {prefix} — K/D {demo.get('kills', 0)}/{demo.get('deaths', 0)}, "
                    f"round {_fmt(demo.get('round_count'))}"
                )
            else:
                lines.append(f"- {prefix} — {_fmt(demo.get('reason', 'okunamadı'))}")
        lines.append("")

    # --- Rifle Mechanics ---
    lines.extend(["### Rifle Mechanics", ""])
    cards = lab.get("per_demo_cards") or agg.get("per_demo_cards") or []
    if cards:
        lines.extend([
            "| Demo | Rifle shots | 1st bullet mov % | Mov % | Long spray % | Güven |",
            "| --- | --- | --- | --- | --- | --- |",
        ])
        for card in cards:
            if card.get("status") != "ok":
                continue
            lines.append(
                f"| `{_fmt(card.get('demo_file'))}` | {_fmt(card.get('rifle_total_shots'))} | "
                f"{_fmt(card.get('rifle_first_bullet_moving_pct'))} | "
                f"{_fmt(card.get('rifle_shots_while_moving_pct'))} | "
                f"{_fmt(card.get('rifle_long_spray_pct'))} | {_fmt(card.get('confidence'))} |"
            )
        lines.append("")

    if mech.get("rifle_reliable"):
        lines.extend([
            "**Combined (rifle-only):**",
            "",
            f"* rifle_total_shots: {_fmt(mech.get('rifle_total_shots'))}",
            f"* rifle_shots_with_velocity: {_fmt(mech.get('rifle_shots_with_velocity'))}",
            f"* rifle_first_bullet_moving_pct: {_fmt(mech.get('rifle_first_bullet_moving_pct'))}",
            f"* rifle_shots_while_moving_pct: {_fmt(mech.get('rifle_shots_while_moving_pct'))}",
            f"* rifle_average_speed_at_shot: {_fmt(mech.get('rifle_average_speed_at_shot'))}",
            f"* rifle_median_speed_at_shot: {_fmt(mech.get('rifle_median_speed_at_shot'))}",
            f"* rifle_spray_length_average: {_fmt(mech.get('rifle_spray_length_average'))}",
            f"* rifle_long_spray_pct: {_fmt(mech.get('rifle_long_spray_pct'))}",
            "",
        ])
        lines.extend(_bullet_list(mech.get("rifle_commentary") or mech.get("counter_strafe_commentary") or []))
    else:
        lines.append("_Rifle velocity verisi yetersiz; counter-strafe teşhisi yapılmadı._")
        lines.append("")

    # --- Proper Counter-Strafe V2 (Experimental — approximate spotted data) ---
    v2 = mech.get("proper_counter_strafe_v2") or {}
    sc = v2.get("source_counts") or {}
    lines.extend([
        f"### {_fmt(v2.get('display_title') or 'Proper Counter-Strafe V2 (Experimental — approximate spotted data)')}",
        "",
        f"- metric_label: `{_fmt(v2.get('metric_label') or 'proper_counter_strafe_v2')}`",
        f"- legacy_metric_label: `{_fmt(v2.get('legacy_metric_label') or mech.get('legacy_metric_label') or 'legacy_first_bullet_moving')}`",
        f"- status: {_fmt(v2.get('status'))}",
        f"- measurement_quality: {_fmt(v2.get('measurement_quality'))}",
        f"- sample_confidence: {_fmt(v2.get('sample_confidence') or v2.get('confidence'))}",
        f"- eligibility_source: {_fmt(v2.get('eligibility_source'))}",
        f"- coach_note: {_fmt(v2.get('coach_soft_label'))} (kesin hata oranı değil)",
        f"- base non-crouched rifle candidates: {_fmt(v2.get('base_rifle_non_crouch_candidates'))}",
        f"- spotted-eligible (headline): {_fmt(v2.get('spotted_eligible_shots') or v2.get('eligible_shots'))}",
        f"- eligibility coverage %: {_fmt(v2.get('eligibility_coverage_pct'))}",
        f"- first-bullet coverage %: {_fmt(v2.get('first_bullet_eligibility_coverage_pct'))}",
        f"- headline proper_counter_strafe_pct: {_fmt(v2.get('proper_counter_strafe_pct'))}",
        f"- headline first_bullet_proper_pct: {_fmt(v2.get('first_bullet_proper_pct'))}",
        f"- median_speed_ratio / p75: {_fmt(v2.get('median_speed_ratio'))} / {_fmt(v2.get('p75_speed_ratio'))}",
        f"- unavailable_reason: {_fmt(v2.get('unavailable_reason'))}",
        "",
        "**Evidence source counts (diagnostic):**",
        f"* spotted_only: n={_fmt((sc.get('spotted_only') or {}).get('n'))} proper%={_fmt((sc.get('spotted_only') or {}).get('proper_counter_strafe_pct'))}",
        f"* spotted_and_hurt: n={_fmt((sc.get('spotted_and_hurt') or {}).get('n'))} proper%={_fmt((sc.get('spotted_and_hurt') or {}).get('proper_counter_strafe_pct'))}",
        f"* hurt_only (excluded from headline): n={_fmt((sc.get('hurt_only') or {}).get('n'))} proper%={_fmt((sc.get('hurt_only') or {}).get('proper_counter_strafe_pct'))}",
        f"* unresolved: n={_fmt((sc.get('unresolved') or {}).get('n'))}",
        "",
    ])
    ak_v2 = (v2.get("by_weapon") or {}).get("ak") or {}
    m4_v2 = (v2.get("by_weapon") or {}).get("m4") or {}
    lines.extend([
        "**V2 AK (headline spotted pool):**",
        f"* eligible: {_fmt(ak_v2.get('eligible_shots'))} | proper%: {_fmt(ak_v2.get('proper_counter_strafe_pct'))} | first_bullet_proper%: {_fmt(ak_v2.get('first_bullet_proper_pct'))} | sample_conf: {_fmt(ak_v2.get('sample_confidence') or ak_v2.get('confidence'))}",
        "",
        "**V2 M4 (headline spotted pool):**",
        f"* eligible: {_fmt(m4_v2.get('eligible_shots'))} | proper%: {_fmt(m4_v2.get('proper_counter_strafe_pct'))} | first_bullet_proper%: {_fmt(m4_v2.get('first_bullet_proper_pct'))} | sample_conf: {_fmt(m4_v2.get('sample_confidence') or m4_v2.get('confidence'))}",
        "",
        "_Headline V2 yalnızca spotted_only + spotted_and_hurt kullanır. hurt_only selection bias nedeniyle hariç. approximate_spotted_mask LoS değildir; measurement_quality=experimental._",
        "",
    ])

    # --- Geometry visibility agreement (diagnostic only) ---
    vis = mech.get("visibility_agreement") or mech.get("geometry_visibility_diagnostic") or {}
    vb = vis.get("buckets") or {}
    lines.extend([
        "### Geometry Visibility Agreement (diagnostic)",
        "",
        f"- status: {_fmt(vis.get('status'))}",
        f"- measurement_quality: {_fmt(vis.get('measurement_quality'))}",
        f"- backend: {_fmt(vis.get('backend_source'))} {_fmt(vis.get('backend_version'))}",
        f"- eye_height_source: {_fmt(vis.get('eye_height_source'))}",
        f"- fov_source: {_fmt(vis.get('fov_source'))}",
        f"- shot_ticks_analyzed: {_fmt(vis.get('shot_ticks_analyzed'))}",
        f"- geometry_resolved_count: {_fmt(vis.get('geometry_resolved_count'))}",
        f"- unavailable_count: {_fmt(vis.get('unavailable_count'))}",
        f"- agreement_pct / disagreement_pct: {_fmt(vis.get('agreement_pct'))} / {_fmt(vis.get('disagreement_pct'))}",
        f"- mean_visible_enemy_count: {_fmt(vis.get('mean_visible_enemy_count'))}",
        f"- geometry_visible_and_spotted: {_fmt(vb.get('geometry_visible_and_spotted'))}",
        f"- geometry_visible_not_spotted: {_fmt(vb.get('geometry_visible_not_spotted'))}",
        f"- geometry_blocked_and_spotted: {_fmt(vb.get('geometry_blocked_and_spotted'))}",
        f"- geometry_blocked_not_spotted: {_fmt(vb.get('geometry_blocked_not_spotted'))}",
        f"- setup_command: `{_fmt(vis.get('setup_command'))}`",
        f"- coach_note: {_fmt(vis.get('coach_note'))}",
        "",
        "_Geometry LoS smoke/flash/prop desteklemez; V2 headline veya legacy metrikleri değiştirmez. Kesin görünürlük hükmü değildir._",
        "",
    ])

    # --- AK vs M4 ---
    lines.extend(["### AK vs M4 Breakdown", ""])
    ak = mech.get("ak_metrics") or {}
    m4 = mech.get("m4_metrics") or {}
    if ak.get("total_shots"):
        lines.extend([
            "**AK (combined):**",
            f"* total_shots: {_fmt(ak.get('total_shots'))}",
            f"* first_bullet_moving_pct: {_fmt(ak.get('first_bullet_moving_pct'))}",
            f"* shots_while_moving_pct: {_fmt(ak.get('shots_while_moving_pct'))}",
            f"* spray_length_average: {_fmt(ak.get('spray_length_average'))}",
            f"* long_spray_pct: {_fmt(ak.get('long_spray_pct'))}",
            "",
        ])
    if m4.get("total_shots"):
        lines.extend([
            "**M4 / M4A1-S (combined):**",
            f"* total_shots: {_fmt(m4.get('total_shots'))}",
            f"* first_bullet_moving_pct: {_fmt(m4.get('first_bullet_moving_pct'))}",
            f"* shots_while_moving_pct: {_fmt(m4.get('shots_while_moving_pct'))}",
            f"* spray_length_average: {_fmt(m4.get('spray_length_average'))}",
            f"* long_spray_pct: {_fmt(m4.get('long_spray_pct'))}",
            "",
        ])
    if not ak.get("total_shots") and not m4.get("total_shots"):
        lines.append("_AK/M4 shot verisi yok._")
        lines.append("")

    # --- Pistol Mechanics ---
    lines.extend(["### Pistol Mechanics", ""])
    if cards:
        lines.extend([
            "| Demo | Pistol shots | 1st bullet mov % | Mov % | Long spam % | Güven |",
            "| --- | --- | --- | --- | --- | --- |",
        ])
        for card in cards:
            if card.get("status") != "ok":
                continue
            lines.append(
                f"| `{_fmt(card.get('demo_file'))}` | {_fmt(card.get('pistol_total_shots'))} | "
                f"{_fmt(card.get('pistol_first_bullet_moving_pct'))} | "
                f"{_fmt(card.get('pistol_shots_while_moving_pct'))} | "
                f"{_fmt(card.get('pistol_long_spam_pct'))} | {_fmt(card.get('pistol_confidence'))} |"
            )
        lines.append("")

    pistol_shots = mech.get("pistol_total_shots", 0) or 0
    if mech.get("pistol_reliable") or pistol_shots > 0:
        lines.extend([
            "**Combined (pistol-only):**",
            "",
            f"* pistol_total_shots: {_fmt(mech.get('pistol_total_shots'))}",
            f"* pistol_shots_with_velocity: {_fmt(mech.get('pistol_shots_with_velocity'))}",
            f"* pistol_average_speed_at_shot: {_fmt(mech.get('pistol_average_speed_at_shot'))}",
            f"* pistol_median_speed_at_shot: {_fmt(mech.get('pistol_median_speed_at_shot'))}",
            f"* pistol_shots_while_moving_pct: {_fmt(mech.get('pistol_shots_while_moving_pct'))}",
            f"* pistol_first_bullet_moving_pct: {_fmt(mech.get('pistol_first_bullet_moving_pct'))}",
            f"* pistol_spam_length_average: {_fmt(mech.get('pistol_spam_length_average'))}",
            f"* pistol_long_spam_pct: {_fmt(mech.get('pistol_long_spam_pct'))}",
            "",
            "**Alt gruplar:**",
            "",
            f"* starter_pistol_total_shots: {_fmt(mech.get('starter_pistol_total_shots'))}",
            f"* starter_pistol_first_bullet_moving_pct: {_fmt(mech.get('starter_pistol_first_bullet_moving_pct'))}",
            f"* starter_pistol_shots_while_moving_pct: {_fmt(mech.get('starter_pistol_shots_while_moving_pct'))}",
            f"* force_pistol_total_shots: {_fmt(mech.get('force_pistol_total_shots'))}",
            f"* force_pistol_first_bullet_moving_pct: {_fmt(mech.get('force_pistol_first_bullet_moving_pct'))}",
            f"* force_pistol_shots_while_moving_pct: {_fmt(mech.get('force_pistol_shots_while_moving_pct'))}",
            f"* deagle_total_shots: {_fmt(mech.get('deagle_total_shots'))}",
            f"* deagle_first_bullet_moving_pct: {_fmt(mech.get('deagle_first_bullet_moving_pct'))}",
            "",
        ])
        rev = mech.get("combined_revolver") or {}
        if rev.get("total_shots"):
            lines.append(f"* revolver_total_shots: {_fmt(rev.get('total_shots'))}")
            lines.append("")
        lines.extend(_bullet_list(mech.get("pistol_commentary") or []))
    else:
        lines.append("_Pistol shot verisi yetersiz._")
        lines.append("")

    # --- SMG Mechanics ---
    lines.extend(["### SMG Mechanics", ""])
    if mech.get("smg_reliable") or (mech.get("smg_total_shots") or 0) > 0:
        lines.extend([
            f"* smg_total_shots: {_fmt(mech.get('smg_total_shots'))}",
            f"* smg_shots_with_velocity: {_fmt(mech.get('smg_shots_with_velocity'))}",
            f"* smg_shots_while_moving_pct: {_fmt(mech.get('smg_shots_while_moving_pct'))}",
            f"* smg_first_bullet_moving_pct: {_fmt(mech.get('smg_first_bullet_moving_pct'))}",
            f"* smg_spray_length_average: {_fmt(mech.get('smg_spray_length_average'))}",
            f"* smg_long_spray_pct: {_fmt(mech.get('smg_long_spray_pct'))}",
            "",
        ])
        lines.extend(_bullet_list(mech.get("smg_commentary") or []))
    else:
        lines.append("_SMG shot verisi yok veya yetersiz._")
        lines.append("")

    # --- Weapon Counts ---
    lines.extend(["### Weapon Counts", ""])
    weapon_counts = mech.get("weapon_shot_counts") or {}
    if weapon_counts:
        for weapon, count in sorted(weapon_counts.items(), key=lambda x: -x[1])[:15]:
            lines.append(f"- {weapon}: {count}")
    else:
        lines.append(f"* Kill silahları: {_fmt(', '.join(agg.get('weapons') or []) or MISSING_DATA_LABEL)}")
    lines.append("")

    # --- Impact / Death Quality ---
    lines.extend(["### Impact / Death Quality", ""])
    impact = agg.get("impact") or {}
    if cards:
        lines.extend([
            "| Demo | K/D | Rounds | Open K/D | Open % | Trade K | Untraded % | Early % | Post-kill surv 5s | Impact | Güven |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ])
        for card in cards:
            if card.get("status") != "ok":
                continue
            k, d = card.get("kills", 0), card.get("deaths", 0)
            kd_str = f"{k}/{d}" if d else f"{k}/0"
            open_kd = f"{_fmt(card.get('opening_kills'))}/{_fmt(card.get('opening_deaths'))}"
            lines.append(
                f"| `{_fmt(card.get('demo_file'))}` | {kd_str} | {_fmt(card.get('round_count'))} | "
                f"{open_kd} | {_fmt(card.get('opening_success_pct'))} | {_fmt(card.get('trade_kills'))} | "
                f"{_fmt(card.get('untraded_death_pct'))} | {_fmt(card.get('early_death_pct'))} | "
                f"{_fmt(card.get('post_kill_survival_rate_5s'))} | {_fmt(card.get('impact_rating_0_100'))} | "
                f"{_fmt(card.get('impact_confidence'))} |"
            )
        lines.append("")

    if impact.get("reliable"):
        lines.extend([
            "**Combined:**",
            "",
            f"* opening_kills / deaths: {_fmt(impact.get('opening_kills'))} / {_fmt(impact.get('opening_deaths'))}",
            f"* opening_duel_success_pct: {_fmt(impact.get('opening_duel_success_pct'))}",
            f"* trade_kills / traded / untraded: {_fmt(impact.get('trade_kills'))} / "
            f"{_fmt(impact.get('traded_deaths'))} / {_fmt(impact.get('untraded_deaths'))}",
            f"* untraded_death_pct: {_fmt(impact.get('untraded_death_pct'))}",
            f"* early_death_pct: {_fmt(impact.get('early_death_pct'))}",
            f"* death_after_kill_within_5s_pct: {_fmt(impact.get('death_after_kill_within_5s_pct'))}",
            f"* post_kill_survival_rate_5s: {_fmt(impact.get('post_kill_survival_rate_5s'))}",
            f"* round_impact_score: {_fmt(impact.get('round_impact_score_total'))} "
            f"({_fmt(impact.get('round_impact_score_per_round'))}/round)",
            f"* impact_rating_0_100: {_fmt(impact.get('impact_rating_0_100'))}",
            f"* unnecessary_death_score: {_fmt(impact.get('unnecessary_death_score'))}",
            "",
        ])
        lines.extend(_bullet_list(impact.get("commentary") or []))
    else:
        reason = impact.get("reason") or "Impact / Death Quality için yeterli demo event verisi yok."
        lines.append(f"_{reason}_")
        lines.append("")

    if lab.get("impact_debug_report_path"):
        lines.extend([
            f"* Impact debug: `{lab['impact_debug_report_path']}`",
            "",
        ])

    # --- Confidence / Limitations ---
    lines.extend([
        "### Confidence / Limitations",
        "",
        f"* Rifle güven: {_fmt(mech.get('rifle_metrics_confidence', lab.get('confidence')))}",
        f"* Pistol güven: {_fmt(mech.get('pistol_metrics_confidence', 'none'))}",
        f"* SMG güven: {_fmt(mech.get('smg_metrics_confidence', 'none'))}",
        f"* Shot+velocity eşleşmesi: {_fmt(agg.get('shots_with_velocity'))} / {_fmt(agg.get('shot_count'))}",
        "",
        "_Counter-strafe teşhisi rifle-only metriklerle yapılır. Pistol ve SMG ayrı değerlendirilir; "
        "SMG/pistol verisi rifle yorumuna karıştırılmaz._",
        "",
    ])

    if mech.get("reliable"):
        lines.extend([
            "### Raw Combined Metrics",
            "",
            "_Tüm silahlar (referans; ana yorum için kullanılmaz):_",
            "",
            f"* total_shots: {_fmt(mech.get('total_shots'))}",
            f"* shots_with_velocity: {_fmt(mech.get('shots_with_velocity'))}",
            f"* shots_while_moving_pct: {_fmt(mech.get('shots_while_moving_pct'))}",
            f"* first_bullet_moving_pct: {_fmt(mech.get('first_bullet_moving_pct'))}",
            f"* spray_length_average: {_fmt(mech.get('spray_length_average'))}",
            f"* long_spray_pct: {_fmt(mech.get('long_spray_pct'))}",
            "",
        ])

    if lab.get("debug_report_paths"):
        lines.extend(["### Debug Raporu", ""])
        for p in lab["debug_report_paths"]:
            lines.append(f"- `{p}`")
        lines.append("")

    lines.extend(_warning_block())
    return lines


def _warning_block() -> list[str]:
    return [
        "### Uyarı",
        "",
        "_Bu mekanik analiz demo parser sürümüdür. Kesin teşhis için daha fazla demo ve hit doğrulaması gerekir._",
        "",
    ]
