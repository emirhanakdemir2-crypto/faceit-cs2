from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config import ensure_data_dirs
from src.storage import CounterStrafeSessionError, init_db, save_counter_strafe_session

console = Console()

LOG_MODE_FLAG = "log_counter_strafe"

REQUIRED_LOG_FIELDS: tuple[tuple[str, str], ...] = (
    ("session_date", "session-date"),
    ("drill_name", "drill-name"),
    ("kills", "kills"),
    ("avg_kill_score", "avg-kill-score"),
    ("avg_speed", "avg-speed"),
    ("avg_timing_ms", "avg-timing-ms"),
    ("avg_technique_pct", "avg-technique-pct"),
    ("hit_accuracy_pct", "hit-accuracy-pct"),
)

OPTIONAL_LOG_FIELDS: tuple[tuple[str, str], ...] = (
    ("notes", "notes"),
    ("evidence_path", "evidence-path"),
)

ALL_LOG_FIELD_NAMES = {name for name, _ in REQUIRED_LOG_FIELDS + OPTIONAL_LOG_FIELDS}

CONFLICTING_ANALYSIS_FLAGS: tuple[tuple[str, str], ...] = (
    ("matches", "--matches"),
    ("days", "--days"),
    ("recent", "--recent"),
    ("post_session", "--post-session"),
    ("ai", "--ai"),
    ("export_ai_prompt", "--export-ai-prompt"),
    ("demo_folder", "--demo-folder"),
    ("mechanics", "--mechanics"),
    ("debug_demo", "--debug-demo"),
    ("tara", "--tara"),
    ("suite", "--suite"),
)


def _is_flag_active(args: argparse.Namespace, attr: str) -> bool:
    if attr in ("matches", "days", "recent", "demo_folder"):
        return getattr(args, attr) is not None
    return bool(getattr(args, attr))


def find_orphan_log_fields(args: argparse.Namespace) -> list[str]:
    if getattr(args, LOG_MODE_FLAG, False):
        return []
    orphans: list[str] = []
    for attr, flag in REQUIRED_LOG_FIELDS + OPTIONAL_LOG_FIELDS:
        if getattr(args, attr, None) is not None:
            orphans.append(f"--{flag}")
    return orphans


def find_conflicting_analysis_flags(args: argparse.Namespace) -> list[str]:
    conflicts: list[str] = []
    for attr, flag in CONFLICTING_ANALYSIS_FLAGS:
        if _is_flag_active(args, attr):
            conflicts.append(flag)
    return conflicts


def find_missing_required_log_fields(args: argparse.Namespace) -> list[str]:
    missing: list[str] = []
    for attr, flag in REQUIRED_LOG_FIELDS:
        if getattr(args, attr, None) is None:
            missing.append(flag)
    return missing


def validate_evidence_path(value: str | None) -> str | None:
    if value is None:
        return None
    path = Path(value.strip())
    if not path.exists():
        raise CounterStrafeSessionError(f"evidence_path mevcut bir dosya olmalı: {value}")
    if not path.is_file():
        raise CounterStrafeSessionError(f"evidence_path mevcut bir dosya olmalı: {value}")
    return str(path)


def _print_error(message: str) -> None:
    console.print(f"[red]{message}[/red]")


def _print_success(session_id: int, payload: dict[str, Any]) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Alan", style="dim")
    table.add_column("Değer", style="bold")
    rows = [
        ("Kayıt ID", session_id),
        ("Nickname", payload["nickname"]),
        ("Session date", payload["session_date"]),
        ("Drill name", payload["drill_name"]),
        ("Kills", payload["kills"]),
        ("Avg kill score", payload["avg_kill_score"]),
        ("Avg speed", payload["avg_speed"]),
        ("Avg timing ms", payload["avg_timing_ms"]),
        ("Avg technique %", payload["avg_technique_pct"]),
        ("Hit accuracy %", payload["hit_accuracy_pct"]),
    ]
    if payload.get("notes"):
        rows.append(("Notes", payload["notes"]))
    if payload.get("evidence_path"):
        rows.append(("Evidence path", payload["evidence_path"]))
    for label, value in rows:
        table.add_row(label, str(value))
    console.print()
    console.print(
        Panel(
            table,
            title="[bold green]Counter-strafe oturumu kaydedildi[/bold green]",
            border_style="green",
        )
    )


def run_counter_strafe_log_cli(args: argparse.Namespace, nickname: str) -> int:
    conflicts = find_conflicting_analysis_flags(args)
    if conflicts:
        joined = ", ".join(conflicts)
        _print_error(
            f"--log-counter-strafe şu analiz seçenekleriyle birlikte kullanılamaz: {joined}"
        )
        return 1

    missing = find_missing_required_log_fields(args)
    if missing:
        joined = ", ".join(f"--{flag}" for flag in missing)
        _print_error(f"Counter-strafe kaydı için eksik zorunlu alanlar: {joined}")
        return 1

    try:
        evidence_path = validate_evidence_path(args.evidence_path)
    except CounterStrafeSessionError as exc:
        _print_error(str(exc))
        return 1

    payload = {
        "nickname": nickname,
        "session_date": args.session_date,
        "drill_name": args.drill_name,
        "kills": args.kills,
        "avg_kill_score": args.avg_kill_score,
        "avg_speed": args.avg_speed,
        "avg_timing_ms": args.avg_timing_ms,
        "avg_technique_pct": args.avg_technique_pct,
        "hit_accuracy_pct": args.hit_accuracy_pct,
        "notes": args.notes,
        "evidence_path": evidence_path,
    }

    ensure_data_dirs()
    init_db()

    try:
        session_id = save_counter_strafe_session(**payload)
    except CounterStrafeSessionError as exc:
        _print_error(str(exc))
        return 1

    _print_success(session_id, payload)
    return 0


def check_orphan_log_args(args: argparse.Namespace) -> int | None:
    orphans = find_orphan_log_fields(args)
    if not orphans:
        return None
    joined = ", ".join(orphans)
    _print_error(
        f"Counter-strafe alanları --log-counter-strafe ile kullanılmalı: {joined}"
    )
    return 1
