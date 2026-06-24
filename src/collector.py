from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.config import GAME_ID, MISSING_DATA_LABEL
from src.faceit_client import FaceitAPIError, FaceitClient

console = Console()


def _safe_get(data: dict[str, Any] | None, *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _stats_has_data(stats: dict[str, Any] | None) -> bool:
    if not stats or not isinstance(stats, dict):
        return False
    rounds = stats.get("rounds")
    return isinstance(rounds, list) and len(rounds) > 0


def collect_player_data(
    client: FaceitClient,
    nickname: str,
    match_count: int = 20,
) -> dict[str, Any]:
    """
    Oyuncu profili, maç geçmişi ve her maç için istatistikleri toplar.
    Eksik verilerde uygulama çökmez; ilgili alanlar işaretlenir.
    """
    result: dict[str, Any] = {
        "nickname": nickname,
        "player": None,
        "player_id": None,
        "history": None,
        "matches": [],
        "errors": [],
        "matches_fetched": 0,
        "stats_success_count": 0,
    }

    try:
        player = client.get_player_by_nickname(nickname)
        result["player"] = player
        result["player_id"] = player.get("player_id")
    except FaceitAPIError as exc:
        msg = exc.user_message or str(exc)
        result["errors"].append(msg)
        console.print(f"[red]{msg}[/red]")
        return result
    except Exception as exc:
        result["errors"].append(f"Oyuncu profili beklenmeyen hata: {exc}")
        return result

    player_id = result["player_id"]
    if not player_id:
        result["errors"].append("Oyuncu player_id bulunamadı.")
        return result

    try:
        history = client.get_player_history(
            player_id,
            nickname,
            game=GAME_ID,
            limit=match_count,
        )
        result["history"] = history
    except FaceitAPIError as exc:
        msg = exc.user_message or str(exc)
        result["errors"].append(msg)
        console.print(f"[yellow]{msg}[/yellow]")
        return result

    items = _safe_get(history, "items", default=[]) or []
    result["matches_fetched"] = len(items)

    if not items:
        result["errors"].append("Maç geçmişi boş veya veri eksik.")
        return result

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Maç istatistikleri (0/{len(items)})",
            total=len(items),
        )

        for index, match_info in enumerate(items, start=1):
            match_id = match_info.get("match_id") if isinstance(match_info, dict) else None
            progress.update(
                task,
                description=f"Maç istatistikleri ({index}/{len(items)})",
            )

            entry: dict[str, Any] = {
                "match_id": match_id or MISSING_DATA_LABEL,
                "history": match_info,
                "stats": None,
                "stats_error": None,
            }

            if not match_id:
                entry["stats_error"] = "match_id veri eksik"
                result["matches"].append(entry)
                progress.advance(task)
                continue

            try:
                stats = client.get_match_stats(match_id)
                entry["stats"] = stats
                if not _stats_has_data(stats):
                    entry["stats_error"] = "Boş stats yanıtı (rounds yok)"
                    result["errors"].append(f"Maç {match_id}: boş stats yanıtı")
                else:
                    result["stats_success_count"] += 1
            except FaceitAPIError as exc:
                entry["stats_error"] = exc.user_message or str(exc)
                result["errors"].append(f"Maç {match_id}: {entry['stats_error']}")
            except Exception as exc:
                entry["stats_error"] = str(exc)
                result["errors"].append(f"Maç {match_id}: beklenmeyen hata — {exc}")

            result["matches"].append(entry)
            progress.advance(task)

    return result
