from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
from src.storage import get_known_match_ids, get_last_analysis, init_db, persist_analysis_run

console = Console()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FACEIT CS2 AI Koçluk — 90 günlük gelişim analizi.",
    )
    parser.add_argument("--nickname", "-n", required=True, help="FACEIT nickname")
    parser.add_argument(
        "--matches", "-m", type=int, default=DEFAULT_MATCH_COUNT,
        help=f"Maks. maç sayısı (varsayılan: {DEFAULT_MATCH_COUNT})",
    )
    parser.add_argument(
        "--days", "-d", type=int, default=DEFAULT_DAYS,
        help=f"Analiz penceresi gün (varsayılan: {DEFAULT_DAYS})",
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
    match_count = max(1, min(args.matches, MAX_MATCH_COUNT))
    days = max(7, min(args.days, 365))

    if not nickname:
        console.print("[red]Nickname boş olamaz.[/red]")
        return 1

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
    console.print(f"Pencere: [yellow]{days}[/yellow] gün / max [yellow]{match_count}[/yellow] maç")
    if args.ai:
        console.print("Gemini AI: [green]açık[/green]")
    if args.export_ai_prompt:
        console.print("AI export: [green]açık[/green]")
    console.print()

    known_before = get_known_match_ids(nickname)
    previous_analysis = get_last_analysis(nickname)

    client = FaceitClient(api_key)
    raw = collect_player_data(client, nickname, match_count=match_count, days=days)

    normalized = normalize_collected_data(raw)
    matches = normalized.get("matches") or []
    summary = compute_performance_summary(matches=matches)
    form = compute_recent_form(normalized, count=5)
    map_stats = compute_map_stats(normalized)
    period_comparison = split_matches_into_periods(matches, days=days)
    period_insights = compare_periods(period_comparison)
    missing_fields = collect_missing_fields(normalized)
    confidence = compute_data_confidence(
        summary.get("total_matches", 0), missing_fields, days=days,
    )

    baseline_summary = None
    if previous_analysis:
        baseline_summary = {
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
        matches, [x for x in new_ids_preview if x], baseline_summary,
    )

    coaching = generate_coaching_draft(
        normalized.get("profile") or {}, summary, form, map_stats,
    )

    demo_folder = Path(args.demo_folder) if args.demo_folder else DEMOS_DIR
    known_ids = {m.get("match_id") for m in matches if m.get("match_id")}
    demo_analysis = scan_demo_folder(demo_folder, known_match_ids=known_ids)

    safe_name = nickname.lower()
    processed_path = PROCESSED_DIR / f"{safe_name}_summary.json"
    report_path = REPORTS_DIR / f"{safe_name}_latest.md"

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
    )

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
        "analysis_window": normalized.get("analysis_window"),
        "matches": matches,
        "collection_errors": normalized.get("collection_errors"),
        "generated_at": normalized.get("generated_at"),
    }

    processed_path.write_text(
        json.dumps(processed_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    ai_export_path: Path | None = None
    if args.export_ai_prompt:
        ai_export_path = write_ai_export(nickname, processed_payload, AI_EXPORTS_DIR)

    ai_comment: str | None = None
    if args.ai:
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
        ai_enabled=args.ai,
        ai_comment=ai_comment,
        ai_export_path=str(ai_export_path) if ai_export_path else None,
    )
    report_path.write_text(report_md, encoding="utf-8")

    panel: dict[str, Any] = {
        "Oyuncu": nickname,
        "Pencere": f"{days} gün / {match_count} maç",
        "Çekilen maç": raw.get("matches_fetched", 0),
        "Stats başarılı": f"{raw.get('stats_success_count', 0)} / {raw.get('matches_fetched', 0)}",
        "Kayıtlı maç": memory.get("stored_matches_total", 0),
        "Yeni maç": memory.get("new_matches_count", 0),
        "Önceki analiz": memory.get("previous_analysis_date") or "—",
        "Rapor": report_path.resolve(),
    }
    if ai_export_path:
        panel["AI export"] = ai_export_path.resolve()
    if demo_analysis.get("found"):
        panel["Demo dosyası"] = len(demo_analysis.get("files") or [])

    _print_summary_panel(**panel)

    if not raw.get("player"):
        console.print("[yellow]Oyuncu verisi alınamadı; rapor kısıtlı oluşturuldu.[/yellow]")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
