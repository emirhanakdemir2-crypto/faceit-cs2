from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.config import GAME_ID, MISSING_DATA_LABEL


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or value == MISSING_DATA_LABEL:
        return None
    try:
        return float(str(value).replace(",", ".").rstrip("%"))
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None or value == "" or value == MISSING_DATA_LABEL:
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _ts_to_iso(ts: int | float | None) -> str:
    if ts is None:
        return MISSING_DATA_LABEL
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OSError):
        return MISSING_DATA_LABEL


def _extract_map_from_stats(stats_payload: dict[str, Any] | None) -> str:
    if not stats_payload:
        return MISSING_DATA_LABEL
    maps: list[str] = []
    for round_data in stats_payload.get("rounds") or []:
        if not isinstance(round_data, dict):
            continue
        round_stats = round_data.get("round_stats") or {}
        if not isinstance(round_stats, dict):
            continue
        map_name = round_stats.get("Map")
        if map_name and map_name not in maps:
            maps.append(str(map_name))
    if not maps:
        return MISSING_DATA_LABEL
    return maps[0] if len(maps) == 1 else ", ".join(maps)

_SUM_KEYS = {
    "Kills",
    "Deaths",
    "Assists",
    "Headshots",
    "MVPs",
    "Triple Kills",
    "Quadro Kills",
    "Penta Kills",
}
_AVG_KEYS = {"ADR", "KAST", "Headshots %", "K/R Ratio"}


def _extract_player_stats_from_match(
    stats_payload: dict[str, Any] | None,
    player_id: str,
) -> dict[str, Any]:
    """Maç stats yanıtından hedef oyuncunun istatistiklerini çıkarır."""
    if not stats_payload:
        return {"available": False, "player_stats": {}, "rounds_played": None}

    rounds = stats_payload.get("rounds") or []
    summed: dict[str, float] = {}
    averaged: dict[str, list[float]] = {k: [] for k in _AVG_KEYS}
    maps_with_data = 0

    for round_data in rounds:
        if not isinstance(round_data, dict):
            continue
        for team in round_data.get("teams") or []:
            if not isinstance(team, dict):
                continue
            for player in team.get("players") or []:
                if not isinstance(player, dict):
                    continue
                if player.get("player_id") != player_id:
                    continue
                maps_with_data += 1
                pstats = player.get("player_stats") or {}
                if not isinstance(pstats, dict):
                    continue
                for key, raw in pstats.items():
                    num = _safe_float(raw)
                    if num is None:
                        continue
                    if key in _SUM_KEYS:
                        summed[key] = summed.get(key, 0.0) + num
                    elif key in _AVG_KEYS:
                        averaged[key].append(num)

    if maps_with_data == 0:
        return {"available": False, "player_stats": {}, "rounds_played": None}

    aggregated: dict[str, float] = dict(summed)
    for key, values in averaged.items():
        if values:
            aggregated[key] = sum(values) / len(values)

    kills = aggregated.get("Kills")
    deaths = aggregated.get("Deaths")
    if kills is not None and deaths is not None and deaths > 0:
        aggregated["K/D Ratio"] = round(kills / deaths, 2)

    return {
        "available": True,
        "player_stats": aggregated,
        "rounds_played": maps_with_data or None,
    }


def _player_won_match(history_item: dict[str, Any], player_id: str) -> bool | None:
    results = history_item.get("results") or {}
    winner = results.get("winner")
    if not winner:
        return None

    teams = history_item.get("teams") or {}
    for faction_key, team in teams.items():
        if not isinstance(team, dict):
            continue
        players = team.get("players") or []
        player_ids = {p.get("player_id") for p in players if isinstance(p, dict)}
        if player_id in player_ids:
            return faction_key == winner
    return None


def normalize_collected_data(raw: dict[str, Any]) -> dict[str, Any]:
    """Ham toplanan veriyi rapor/metrik için normalize eder."""
    player = raw.get("player") or {}
    player_id = raw.get("player_id") or player.get("player_id")
    nickname = raw.get("nickname") or player.get("nickname") or MISSING_DATA_LABEL

    games = player.get("games") or {}
    cs2_game = games.get(GAME_ID) or {}

    profile_url = (
        f"https://www.faceit.com/en/players/{nickname}"
        if nickname and nickname != MISSING_DATA_LABEL
        else MISSING_DATA_LABEL
    )

    profile = {
        "nickname": nickname,
        "player_id": player_id or MISSING_DATA_LABEL,
        "country": player.get("country") or MISSING_DATA_LABEL,
        "avatar": player.get("avatar") or MISSING_DATA_LABEL,
        "faceit_url": profile_url,
        "skill_level": cs2_game.get("skill_level") if cs2_game else MISSING_DATA_LABEL,
        "faceit_elo": cs2_game.get("faceit_elo") if cs2_game else MISSING_DATA_LABEL,
        "game_player_name": cs2_game.get("game_player_name") if cs2_game else MISSING_DATA_LABEL,
    }

    normalized_matches: list[dict[str, Any]] = []

    for entry in raw.get("matches") or []:
        history_item = entry.get("history") or {}
        stats_payload = entry.get("stats")
        map_name = _extract_map_from_stats(stats_payload)
        extracted = _extract_player_stats_from_match(stats_payload, player_id or "")
        pstats = extracted["player_stats"]

        kills = _safe_int(pstats.get("Kills"))
        deaths = _safe_int(pstats.get("Deaths"))
        assists = _safe_int(pstats.get("Assists"))
        kd = _safe_float(pstats.get("K/D Ratio"))
        if kd is None and kills is not None and deaths is not None and deaths > 0:
            kd = round(kills / deaths, 2)

        normalized_matches.append(
            {
                "match_id": entry.get("match_id") or MISSING_DATA_LABEL,
                "finished_at": _ts_to_iso(history_item.get("finished_at")),
                "started_at": _ts_to_iso(history_item.get("started_at")),
                "map": map_name,
                "game_mode": history_item.get("game_mode") or MISSING_DATA_LABEL,
                "competition_name": history_item.get("competition_name") or MISSING_DATA_LABEL,
                "match_type": history_item.get("match_type") or MISSING_DATA_LABEL,
                "region": history_item.get("region") or MISSING_DATA_LABEL,
                "won": _player_won_match(history_item, player_id or ""),
                "stats_available": extracted["available"] and not entry.get("stats_error"),
                "stats_error": entry.get("stats_error"),
                "kills": kills if kills is not None else MISSING_DATA_LABEL,
                "deaths": deaths if deaths is not None else MISSING_DATA_LABEL,
                "assists": assists if assists is not None else MISSING_DATA_LABEL,
                "kd_ratio": kd if kd is not None else MISSING_DATA_LABEL,
                "kr_ratio": (
                    _safe_float(pstats.get("K/R Ratio"))
                    if _safe_float(pstats.get("K/R Ratio")) is not None
                    else MISSING_DATA_LABEL
                ),
                "adr": (
                    _safe_float(pstats.get("ADR"))
                    if _safe_float(pstats.get("ADR")) is not None
                    else MISSING_DATA_LABEL
                ),
                "headshots": (
                    _safe_int(pstats.get("Headshots"))
                    if _safe_int(pstats.get("Headshots")) is not None
                    else MISSING_DATA_LABEL
                ),
                "headshot_pct": (
                    _safe_float(pstats.get("Headshots %"))
                    if _safe_float(pstats.get("Headshots %")) is not None
                    else MISSING_DATA_LABEL
                ),
                "mvps": (
                    _safe_int(pstats.get("MVPs"))
                    if _safe_int(pstats.get("MVPs")) is not None
                    else MISSING_DATA_LABEL
                ),
                "kast": (
                    _safe_float(pstats.get("KAST"))
                    if _safe_float(pstats.get("KAST")) is not None
                    else MISSING_DATA_LABEL
                ),
                "triple_kills": (
                    _safe_int(pstats.get("Triple Kills"))
                    if _safe_int(pstats.get("Triple Kills")) is not None
                    else MISSING_DATA_LABEL
                ),
                "quadro_kills": (
                    _safe_int(pstats.get("Quadro Kills"))
                    if _safe_int(pstats.get("Quadro Kills")) is not None
                    else MISSING_DATA_LABEL
                ),
                "penta_kills": (
                    _safe_int(pstats.get("Penta Kills"))
                    if _safe_int(pstats.get("Penta Kills")) is not None
                    else MISSING_DATA_LABEL
                ),
                "rounds_played": extracted["rounds_played"] or MISSING_DATA_LABEL,
            }
        )

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "nickname": nickname,
        "profile": profile,
        "match_count_requested": len(raw.get("matches") or []),
        "matches": normalized_matches,
        "collection_errors": raw.get("errors") or [],
    }
