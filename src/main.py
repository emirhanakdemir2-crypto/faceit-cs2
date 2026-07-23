from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.ai_export import write_ai_export
from src.coaching import generate_coaching_draft
from src.collector import collect_player_data
from src.config import (
    AI_EXPORTS_DIR,
    DEFAULT_DAYS,
    DEFAULT_MATCH_COUNT,
    DEMOS_DIR,
    MAX_MATCH_COUNT,
    PROCESSED_DIR,
    REPORTS_DIR,
    ensure_data_dirs,
    get_api_key,
)
from src.demo_analyzer import scan_demo_folder
from src.mechanics_lab import render_mechanics_lab_markdown, run_mechanics_lab
from src.faceit_client import FaceitClient
from src.gemini_client import generate_coaching_comment
from src.metrics import (
    collect_missing_fields,
    compute_data_confidence,
    compute_map_stats,
    compute_new_matches_baseline,
    compute_performance_summary,
    compute_persistent_problems,
    compute_recent_form,
)
from src.normalizer import normalize_collected_data
from src.period_analysis import compare_periods, split_matches_into_periods
from src.report_writer import write_markdown_report
from src.analytics_suite import build_analytics_suite, write_suite_report
from src.dashboard_export import write_dashboard_html
from src.session_coach import (
    build_session_coach,
    load_cached_baseline,
    write_clip_review_template,
)
from src.storage import get_known_match_ids, get_last_analysis, init_db, persist_analysis_run
from src.counter_strafe_cli import check_orphan_log_args, run_counter_strafe_log_cli

console = Console()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FACEIT CS2 AI Koçluk — 90 günlük gelişim analizi.",
    )
    parser.add_argument("--nickname", "-n", required=True, help="FACEIT nickname")
    parser.add_argument(
        "--matches", "-m", type=int, default=None,
        help=f"Maks. maç sayısı (varsayılan: {DEFAULT_MATCH_COUNT})",
    )
    parser.add_argument(
        "--days", "-d", type=int, default=None,
        help=f"Analiz penceresi gün (varsayılan: {DEFAULT_DAYS})",
    )
    parser.add_argument(
        "--recent", "-r", type=int, default=None,
        help="Son N maç formu (örn. 5, 10, 20) — session coach kıyası",
    )
    parser.add_argument(
        "--post-session", action="store_true",
        help="Maç sonrası koçluk raporu (baseline vs son form)",
    )
    parser.add_argument("--ai", action="store_true", help="Gemini AI yorumu üret")
    parser.add_argument(
        "--export-ai-prompt", action="store_true",
        help="AI export belgesi oluştur (data/ai_exports/)",
    )
    parser.add_argument(
        "--demo-folder", type=str, default=None,
        help="Manuel demo klasörü (örn. data/demos)",
    )
    parser.add_argument(
        "--mechanics", action="store_true",
        help="Demo parser ile mekanik analiz (opsiyonel, demoparser2)",
    )
    parser.add_argument(
        "--debug-demo", action="store_true",
        help="Demo parser debug raporu (data/reports/)",
    )
    parser.add_argument(
        "--tara", action="store_true",
        help="FACEIT + demo mechanics + analytics suite + ChatGPT tara raporu",
    )
    parser.add_argument(
        "--suite", action="store_true",
        help="Coach Analytics Suite raporu + dashboard HTML",
    )
    parser.add_argument(
        "--log-counter-strafe", action="store_true",
        help="Doğrulanmış counter-strafe oturumunu kaydet (FACEIT analizi çalıştırmaz)",
    )
    parser.add_argument("--session-date", type=str, default=None, help="Counter-strafe oturum tarihi (YYYY-MM-DD)")
    parser.add_argument("--drill-name", type=str, default=None, help="Counter-strafe drill/map adı")
    parser.add_argument("--kills", type=int, default=None, help="Counter-strafe kill sayısı")
    parser.add_argument("--avg-kill-score", type=float, default=None, help="Counter-strafe avg kill score")
    parser.add_argument("--avg-speed", type=float, default=None, help="Counter-strafe avg speed")
    parser.add_argument("--avg-timing-ms", type=float, default=None, help="Counter-strafe avg timing (ms)")
    parser.add_argument("--avg-technique-pct", type=float, default=None, help="Counter-strafe avg technique %")
    parser.add_argument("--hit-accuracy-pct", type=float, default=None, help="Counter-strafe hit accuracy %")
    parser.add_argument("--notes", type=str, default=None, help="Counter-strafe oturum notu (opsiyonel)")
    parser.add_argument(
        "--evidence-path", type=str, default=None,
        help="Screenshot kanıt dosya yolu (opsiyonel, mevcut dosya olmalı)",
    )
    return parser.parse_args(argv)


def _print_summary_panel(**kwargs: Any) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Alan", style="dim")
    table.add_column("Değer", style="bold")
    for key, val in kwargs.items():
        table.add_row(key, str(val))
    console.print()
    console.print(Panel(table, title="[bold green]Tamamlandı[/bold green]", border_style="green"))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    nickname = args.nickname.strip()

    if not nickname:
        console.print("[red]Nickname boş olamaz.[/red]")
        return 1

    orphan_exit = check_orphan_log_args(args)
    if orphan_exit is not None:
        return orphan_exit

    if args.log_counter_strafe:
        return run_counter_strafe_log_cli(args, nickname)

    if args.tara:
        if not args.demo_folder:
            args.demo_folder = str(DEMOS_DIR)
        args.mechanics = True
        args.suite = True

    if args.suite:
        if not args.demo_folder:
            args.demo_folder = str(DEMOS_DIR)
        args.mechanics = True

    days = max(7, min(args.days if args.days is not None else DEFAULT_DAYS, 365))
    match_count = max(
        1, min(args.matches if args.matches is not None else DEFAULT_MATCH_COUNT, MAX_MATCH_COUNT),
    )

    session_enabled = args.post_session or args.recent is not None
    recent_count = args.recent if args.recent is not None else (10 if args.post_session else None)
    form_only = (
        session_enabled
        and not args.post_session
        and args.matches is None
        and args.days is None
    )

    if session_enabled and recent_count is not None:
        recent_count = max(1, min(recent_count, MAX_MATCH_COUNT))

    if form_only and recent_count is not None:
        api_match_count = recent_count
    elif args.post_session and recent_count is not None:
        api_match_count = max(recent_count, 20)
    else:
        api_match_count = match_count

    ensure_data_dirs()
    init_db()

    try:
        api_key = get_api_key()
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    console.print()
    console.print("[bold cyan]FACEIT CS2 Koçluk[/bold cyan]")
    console.print(f"Oyuncu: [bold green]{nickname}[/bold green]")
    if session_enabled:
        mode = "post-session" if args.post_session else ("form-only" if form_only else "session+full")
        console.print(
            f"Session Coach: [green]{mode}[/green] / son [yellow]{recent_count}[/yellow] maç"
        )
    console.print(f"Pencere: [yellow]{days}[/yellow] gün / max [yellow]{api_match_count}[/yellow] maç")
    if args.ai:
        console.print("Gemini AI: [green]açık[/green]")
    if args.export_ai_prompt:
        console.print("AI export: [green]açık[/green]")
    if args.mechanics:
        console.print("Mechanics Lab: [green]açık[/green]")
    if args.suite:
        console.print("Analytics Suite: [green]açık[/green]")
    if args.tara:
        console.print("Tara modu: [green]açık[/green]")
    if args.debug_demo:
        console.print("Demo debug: [green]açık[/green]")
    console.print()

    known_before = get_known_match_ids(nickname)
    previous_analysis = get_last_analysis(nickname)
    cached_baseline = load_cached_baseline(nickname, PROCESSED_DIR)

    client = FaceitClient(api_key)
    raw = collect_player_data(client, nickname, match_count=api_match_count, days=days)

    normalized = normalize_collected_data(raw)
    matches = normalized.get("matches") or []

    needs_full_baseline = session_enabled and (
        (form_only or args.post_session) and cached_baseline is None
    )
    if needs_full_baseline and len(matches) < max(match_count, 30):
        if form_only or args.post_session:
            if cached_baseline is None:
                console.print("[dim]Baseline için tam pencere çekiliyor...[/dim]")
                raw_full = collect_player_data(
                    client, nickname, match_count=match_count, days=days,
                )
                normalized_full = normalize_collected_data(raw_full)
                full_matches = normalized_full.get("matches") or []
                if full_matches:
                    matches = full_matches
                    normalized = normalized_full
                    raw = raw_full

    summary = compute_performance_summary(matches=matches)
    form = compute_recent_form(normalized, count=5)
    map_stats = compute_map_stats(normalized)

    baseline_summary = summary
    baseline_map_stats = map_stats
    if (form_only or args.post_session) and cached_baseline and len(matches) < match_count:
        baseline_summary, baseline_map_stats = cached_baseline

    session_coach: dict[str, Any] | None = None
    clip_template_path: Path | None = None
    if session_enabled and recent_count is not None:
        session_coach = build_session_coach(
            matches,
            baseline_summary,
            baseline_map_stats,
            recent_count=recent_count,
            days=days,
        )
        clip_template_path = write_clip_review_template(
            REPORTS_DIR / f"{nickname.lower()}_clip_review_template.md",
            nickname,
        )

    period_comparison = split_matches_into_periods(matches, days=days)
    period_insights = compare_periods(period_comparison)
    missing_fields = collect_missing_fields(normalized)
    confidence = compute_data_confidence(
        summary.get("total_matches", 0), missing_fields, days=days,
    )

    prev_baseline_summary = None
    if previous_analysis:
        prev_baseline_summary = {
            "win_rate_pct": previous_analysis.get("win_rate"),
            "avg_kd_ratio": previous_analysis.get("kd"),
            "avg_adr": previous_analysis.get("adr"),
            "avg_headshot_pct": previous_analysis.get("hs_percent"),
            "avg_kast": previous_analysis.get("kast"),
        }

    new_ids_preview = [
        m.get("match_id") for m in matches
        if m.get("match_id") and m.get("match_id") not in known_before
    ]
    new_matches_baseline = compute_new_matches_baseline(
        matches, [x for x in new_ids_preview if x], prev_baseline_summary,
    )

    coaching = generate_coaching_draft(
        normalized.get("profile") or {}, summary, form, map_stats,
    )

    demo_folder = Path(args.demo_folder) if args.demo_folder else DEMOS_DIR
    known_ids = {m.get("match_id") for m in matches if m.get("match_id")}
    demo_analysis = scan_demo_folder(demo_folder, known_match_ids=known_ids)

    mechanics_lab: dict[str, Any] | None = None
    demo_note: str | None = None
    if args.mechanics:
        mechanics_lab = run_mechanics_lab(
            demo_folder,
            nickname,
            debug_demo=args.debug_demo,
            debug_report_dir=REPORTS_DIR,
        )
        if mechanics_lab.get("status") == "unavailable":
            demo_note = "Demo bulunamadı, sadece FACEIT raporu üretildi."
            if not args.tara:
                console.print(f"[yellow]{demo_note}[/yellow]")

    safe_name = nickname.lower()
    if args.post_session:
        report_path = REPORTS_DIR / f"{safe_name}_session_latest.md"
    elif form_only:
        report_path = REPORTS_DIR / f"{safe_name}_form_latest.md"
    else:
        report_path = REPORTS_DIR / f"{safe_name}_latest.md"
    processed_path = PROCESSED_DIR / f"{safe_name}_summary.json"

    skip_full_persist = form_only or args.post_session
    memory: dict[str, Any] = {}
    if not skip_full_persist:
        memory = persist_analysis_run(
            nickname,
            raw.get("player_id"),
            matches,
            summary,
            map_stats,
            coaching,
            str(report_path),
            known_before,
            days=days,
            requested_matches=match_count,
            period_metrics=period_comparison,
            mechanics_lab=mechanics_lab,
        )
    else:
        memory = {
            "stored_matches_total": len(known_before),
            "new_matches_count": len(new_ids_preview),
            "previous_analysis_date": (
                previous_analysis.get("created_at") if previous_analysis else None
            ),
            "status_message": "Session coach modu — tam analiz kaydı atlandı.",
            "improved_areas": [],
            "worsened_areas": [],
            "focus_plan_7d": [],
        }

    persistent_problems = compute_persistent_problems(summary, period_comparison, memory)

    processed_payload = {
        "profile": normalized.get("profile"),
        "summary": summary,
        "recent_form": form,
        "map_stats": map_stats,
        "period_comparison": period_comparison,
        "period_insights": period_insights,
        "persistent_problems": persistent_problems,
        "new_matches_baseline": new_matches_baseline,
        "data_confidence": confidence,
        "missing_fields": missing_fields,
        "coaching_draft": coaching,
        "memory": memory,
        "demo_analysis": demo_analysis,
        "mechanics_lab": mechanics_lab,
        "session_coach": session_coach,
        "analysis_window": normalized.get("analysis_window"),
        "matches": matches,
        "collection_errors": normalized.get("collection_errors"),
        "generated_at": normalized.get("generated_at"),
    }

    if not skip_full_persist:
        processed_path.write_text(
            json.dumps(processed_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    ai_export_path: Path | None = None
    if args.export_ai_prompt and not skip_full_persist:
        ai_export_path = write_ai_export(nickname, processed_payload, AI_EXPORTS_DIR)

    ai_comment: str | None = None
    if args.ai and not skip_full_persist:
        console.print("[dim]Gemini AI koçluk yorumu üretiliyor...[/dim]")
        ai_comment = generate_coaching_comment(processed_payload)

    report_md = write_markdown_report(
        normalized,
        summary,
        form=form,
        map_stats=map_stats,
        missing_fields=missing_fields,
        coaching=coaching,
        memory=memory,
        confidence=confidence,
        period_comparison=period_comparison,
        period_insights=period_insights,
        persistent_problems=persistent_problems,
        new_matches_baseline=new_matches_baseline,
        demo_analysis=demo_analysis,
        mechanics_lab=mechanics_lab,
        ai_enabled=args.ai,
        ai_comment=ai_comment,
        ai_export_path=str(ai_export_path) if ai_export_path else None,
        session_coach=session_coach,
        session_only=form_only or args.post_session,
    )
    report_path.write_text(report_md, encoding="utf-8")

    suite_data: dict[str, Any] | None = None
    suite_path: Path | None = None
    dashboard_path: Path | None = None
    tara_path: Path | None = None
    clipboard_ok = False

    if args.suite or args.tara:
        processed_payload["mechanics_lab"] = mechanics_lab
        suite_data = build_analytics_suite(
            processed_payload,
            memory=memory,
            demo_folder=demo_folder,
        )
        processed_payload["analytics_suite"] = suite_data
        suite_path = write_suite_report(nickname, suite_data, REPORTS_DIR)
        dashboard_path = write_dashboard_html(suite_data, REPORTS_DIR, nickname)

    if args.tara:
        from src.tara_export import copy_tara_to_clipboard, write_tara_export
        tara_path = write_tara_export(
            nickname,
            processed_payload,
            AI_EXPORTS_DIR,
            demo_note=demo_note,
        )
        tara_content = tara_path.read_text(encoding="utf-8")
        clipboard_ok = copy_tara_to_clipboard(tara_content)

    if args.tara:
        console.print()
        console.print("[bold green]Tara tamamlandı.[/bold green]")
        console.print(f"Detaylı rapor: {report_path.resolve()}")
        if suite_path:
            console.print(f"Suite raporu: {suite_path.resolve()}")
        if dashboard_path:
            console.print(f"Dashboard HTML: {dashboard_path.resolve()}")
        if tara_path:
            console.print(f"ChatGPT raporu: {tara_path.resolve()}")
        if demo_note:
            console.print(f"[yellow]{demo_note}[/yellow]")
        if clipboard_ok:
            console.print("Panoya kopyalandı.")
        else:
            console.print("Panoya kopyalanamadı, dosyadan kopyalayın.")
        if not raw.get("player"):
            console.print("[yellow]Oyuncu verisi alınamadı; rapor kısıtlı oluşturuldu.[/yellow]")
            return 1
        return 0

    if args.suite:
        console.print()
        console.print("[bold green]Analytics Suite tamamlandı.[/bold green]")
        console.print(f"Detaylı rapor: {report_path.resolve()}")
        if suite_path:
            console.print(f"Suite raporu: {suite_path.resolve()}")
        if dashboard_path:
            console.print(f"Dashboard HTML: {dashboard_path.resolve()}")
        if demo_note:
            console.print(f"[yellow]{demo_note}[/yellow]")

    panel: dict[str, Any] = {
        "Oyuncu": nickname,
        "Pencere": f"{days} gün / {api_match_count} maç",
        "Çekilen maç": raw.get("matches_fetched", 0),
        "Stats başarılı": f"{raw.get('stats_success_count', 0)} / {raw.get('matches_fetched', 0)}",
        "Rapor": report_path.resolve(),
    }
    if session_coach:
        panel["Focus Risk Score"] = session_coach.get("focus_risk", {}).get("score", "—")
        panel["Queue kararı"] = session_coach.get("focus_risk", {}).get("queue_decision", "—")
    if clip_template_path:
        panel["Clip template"] = clip_template_path.resolve()
    if not skip_full_persist:
        panel["Kayıtlı maç"] = memory.get("stored_matches_total", 0)
        panel["Yeni maç"] = memory.get("new_matches_count", 0)
        panel["Önceki analiz"] = memory.get("previous_analysis_date") or "—"
    if ai_export_path:
        panel["AI export"] = ai_export_path.resolve()
    if mechanics_lab:
        panel["Mechanics Lab"] = mechanics_lab.get("status", "—")
        panel["Demo güven"] = mechanics_lab.get("confidence", "—")
        if mechanics_lab.get("debug_report_paths"):
            panel["Debug rapor"] = mechanics_lab["debug_report_paths"][0]
    if demo_analysis.get("found"):
        panel["Demo dosyası"] = len(demo_analysis.get("files") or [])

    _print_summary_panel(**panel)

    if not raw.get("player"):
        console.print("[yellow]Oyuncu verisi alınamadı; rapor kısıtlı oluşturuldu.[/yellow]")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
