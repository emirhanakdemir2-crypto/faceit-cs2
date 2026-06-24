from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.coaching import generate_coaching_draft
from src.collector import collect_player_data
from src.config import (
    DEFAULT_MATCH_COUNT,
    PROCESSED_DIR,
    REPORTS_DIR,
    ensure_data_dirs,
    get_api_key,
)
from src.faceit_client import FaceitClient
from src.gemini_client import generate_coaching_comment
from src.metrics import (
    collect_missing_fields,
    compute_data_confidence,
    compute_map_stats,
    compute_performance_summary,
    compute_recent_form,
)
from src.normalizer import normalize_collected_data
from src.report_writer import write_markdown_report
from src.storage import get_known_match_ids, init_db, persist_analysis_run

console = Console()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FACEIT CS2 AI Koçluk Aracı — oyuncu performans raporu üretir.",
    )
    parser.add_argument(
        "--nickname",
        "-n",
        required=True,
        help="FACEIT oyuncu nickname'i",
    )
    parser.add_argument(
        "--matches",
        "-m",
        type=int,
        default=DEFAULT_MATCH_COUNT,
        help=f"Analiz edilecek son maç sayısı (varsayılan: {DEFAULT_MATCH_COUNT})",
    )
    parser.add_argument(
        "--ai",
        action="store_true",
        help="Gemini AI koçluk yorumu üret (GEMINI_API_KEY gerekir)",
    )
    return parser.parse_args(argv)


def _print_summary_panel(
    nickname: str,
    matches_requested: int,
    matches_fetched: int,
    stats_success: int,
    stored_total: int,
    new_matches: int,
    previous_analysis_date: str | None,
    report_path: Path,
    processed_path: Path,
) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Alan", style="dim")
    table.add_column("Değer", style="bold")

    table.add_row("Oyuncu", nickname)
    table.add_row("İstenen maç", str(matches_requested))
    table.add_row("Çekilen maç", str(matches_fetched))
    table.add_row("Stats başarılı", f"{stats_success} / {matches_fetched}")
    table.add_row("Toplam kayıtlı maç", str(stored_total))
    table.add_row("Yeni maç", str(new_matches))
    table.add_row(
        "Önceki analiz",
        previous_analysis_date if previous_analysis_date else "— (ilk analiz)",
    )
    table.add_row("İşlenmiş özet", str(processed_path.resolve()))
    table.add_row("Rapor dosyası", str(report_path.resolve()))

    console.print()
    console.print(
        Panel(
            table,
            title="[bold green]Tamamlandı[/bold green]",
            border_style="green",
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    nickname = args.nickname.strip()
    match_count = max(1, min(args.matches, 100))

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
    console.print(f"Analiz: son [yellow]{match_count}[/yellow] maç")
    if args.ai:
        console.print("Gemini AI: [green]açık[/green]")
    console.print()

    known_before = get_known_match_ids(nickname)

    client = FaceitClient(api_key)
    raw = collect_player_data(client, nickname, match_count=match_count)

    normalized = normalize_collected_data(raw)
    summary = compute_performance_summary(normalized)
    form = compute_recent_form(normalized, count=5)
    map_stats = compute_map_stats(normalized)
    missing_fields = collect_missing_fields(normalized)
    confidence = compute_data_confidence(
        summary.get("total_matches", 0),
        missing_fields,
    )
    coaching = generate_coaching_draft(
        normalized.get("profile") or {},
        summary,
        form,
        map_stats,
    )

    safe_name = nickname.lower()
    processed_path = PROCESSED_DIR / f"{safe_name}_summary.json"
    report_path = REPORTS_DIR / f"{safe_name}_latest.md"

    memory = persist_analysis_run(
        nickname,
        raw.get("player_id"),
        normalized.get("matches") or [],
        summary,
        map_stats,
        coaching,
        str(report_path),
        known_before,
    )

    processed_payload = {
        "profile": normalized.get("profile"),
        "summary": summary,
        "recent_form": form,
        "map_stats": map_stats,
        "data_confidence": confidence,
        "missing_fields": missing_fields,
        "coaching_draft": coaching,
        "memory": memory,
        "matches": normalized.get("matches"),
        "collection_errors": normalized.get("collection_errors"),
        "generated_at": normalized.get("generated_at"),
    }

    processed_path.write_text(
        json.dumps(processed_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

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
        ai_enabled=args.ai,
        ai_comment=ai_comment,
    )
    report_path.write_text(report_md, encoding="utf-8")

    _print_summary_panel(
        nickname=nickname,
        matches_requested=match_count,
        matches_fetched=raw.get("matches_fetched", 0),
        stats_success=raw.get("stats_success_count", 0),
        stored_total=memory.get("stored_matches_total", 0),
        new_matches=memory.get("new_matches_count", 0),
        previous_analysis_date=memory.get("previous_analysis_date"),
        report_path=report_path,
        processed_path=processed_path,
    )

    if not raw.get("player"):
        console.print("[yellow]Oyuncu verisi alınamadı; rapor kısıtlı oluşturuldu.[/yellow]")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
