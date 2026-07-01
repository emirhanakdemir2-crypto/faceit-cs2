from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from src.death_quality import (
    compute_unnecessary_death_score,
    generate_death_quality_commentary,
    generate_impact_commentary,
    generate_opening_commentary,
    generate_trade_commentary,
)
from src.demo_parser import _df_records, _row_player_name, _row_steamid, demoparser_available

TICK_RATE = 64
TRADE_WINDOW_SEC = 5
EARLY_DEATH_SEC = 20
TRADE_WINDOW_TICKS = TRADE_WINDOW_SEC * TICK_RATE
EARLY_DEATH_TICKS = EARLY_DEATH_SEC * TICK_RATE


def _empty_impact(*, reason: str = "", confidence: str = "none") -> dict[str, Any]:
    return {
        "reliable": False,
        "metrics_confidence": confidence,
        "source": "Unavailable",
        "reason": reason,
        "unavailable_reasons": [reason] if reason else [],
    }


def _pct(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return round(num / den * 100, 1)


def _build_team_map(player_info: Any) -> dict[int, int]:
    teams: dict[int, int] = {}
    for row in _df_records(player_info):
        sid = _row_steamid(row)
        team = row.get("team_number")
        if sid is not None and team is not None:
            try:
                teams[sid] = int(team)
            except (TypeError, ValueError):
                pass
    return teams


def _parse_steamid_val(val: Any) -> int | None:
    if val in (None, ""):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _parse_death_rows(death_df: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _df_records(death_df):
        tick = row.get("tick")
        rnd = row.get("total_rounds_played") or row.get("round")
        att_sid = _parse_steamid_val(row.get("attacker_steamid"))
        vic_sid = _parse_steamid_val(row.get("user_steamid"))
        if vic_sid is None:
            vic_sid = _row_steamid(row)
        try:
            tick_i = int(tick) if tick is not None else None
            rnd_i = int(rnd) if rnd is not None else None
        except (TypeError, ValueError):
            continue
        if tick_i is None or rnd_i is None:
            continue
        attacker = _row_player_name(row, "attacker_name", "attackerName")
        victim = _row_player_name(row, "user_name", "name", "victim_name")
        if not victim:
            continue
        rows.append({
            "tick": tick_i,
            "round": rnd_i,
            "attacker_steamid": att_sid,
            "victim_steamid": vic_sid,
            "attacker_name": attacker,
            "victim_name": victim,
            "weapon": _row_player_name(row, "weapon", "weapon_name"),
        })
    return rows


def _parse_round_starts(parser: Any, events: list[str]) -> dict[int, int]:
    """round -> start tick."""
    starts: dict[int, int] = {}
    for ev in ("round_freeze_end", "round_start", "round_officially_started"):
        if ev not in events:
            continue
        try:
            df = parser.parse_event(ev, other=["tick", "total_rounds_played", "round"])
            for row in _df_records(df):
                tick = row.get("tick")
                rnd = row.get("total_rounds_played") or row.get("round")
                if tick is None or rnd is None:
                    continue
                try:
                    r = int(rnd)
                    t = int(tick)
                except (TypeError, ValueError):
                    continue
                if r not in starts or t < starts[r]:
                    starts[r] = t
        except Exception:
            continue
    return starts


def _is_player(
    steamid: int | None,
    name: str | None,
    player_sid: int | None,
    player_name: str,
    nickname: str,
) -> bool:
    if player_sid is not None and steamid is not None and steamid == player_sid:
        return True
    if not name:
        return False
    nick = nickname.strip().lower()
    target = player_name.strip().lower()
    nl = name.lower()
    return nl == target or nick in nl or nl in nick


def analyze_death_events(
    deaths: list[dict[str, Any]],
    *,
    player_steamid: int | None,
    player_name: str,
    nickname: str,
    team_map: dict[int, int],
    round_starts: dict[int, int],
) -> dict[str, Any]:
    unavailable: list[str] = []
    if not deaths:
        return _empty_impact(reason="player_death eventi yok.")

    player_team = team_map.get(player_sid) if (player_sid := player_steamid) else None
    if not team_map:
        unavailable.append("team_number bilgisi eksik — trade metrikleri sınırlı.")
    if not round_starts:
        unavailable.append("round_start tick yok — early death için round içi min tick kullanıldı.")

    # round start fallback: min death tick per round
    round_min_tick: dict[int, int] = {}
    for d in deaths:
        r = d["round"]
        round_min_tick[r] = min(round_min_tick.get(r, d["tick"]), d["tick"])

    def round_start_tick(r: int) -> int:
        if r in round_starts:
            return round_starts[r]
        return round_min_tick.get(r, 0)

    # Group by round
    by_round: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for d in deaths:
        if d.get("attacker_steamid") and d["attacker_steamid"] == d.get("victim_steamid"):
            continue
        if not d.get("attacker_steamid"):
            continue
        by_round[d["round"]].append(d)

    opening_kills = opening_deaths = 0
    t_open_k = t_open_d = ct_open_k = ct_open_d = 0
    side_reliable = player_team is not None

    trade_kills = 0
    traded_deaths = 0
    untraded_deaths = 0
    trade_times: list[int] = []

    player_kills: list[tuple[int, int]] = []  # (round, tick)
    player_deaths: list[tuple[int, int, int | None]] = []  # round, tick, killer_sid

    early_deaths = 0
    death_after_kill_5s = 0
    death_after_kill_10s = 0
    kills_with_survival_5s = 0
    kills_with_survival_10s = 0

    deaths_advantage = deaths_disadvantage = deaths_even = 0
    team_state_reliable = bool(team_map)

    round_impacts: dict[int, int] = defaultdict(int)
    rounds_analyzed = len(by_round)

    for rnd, round_deaths in by_round.items():
        sorted_deaths = sorted(round_deaths, key=lambda x: x["tick"])
        team_deaths_in_round: dict[int, int] = defaultdict(int)

        first = sorted_deaths[0]
        att = first["attacker_steamid"]
        vic = first["victim_steamid"]
        if _is_player(att, first["attacker_name"], player_sid, player_name, nickname):
            opening_kills += 1
            round_impacts[rnd] += 3
            if side_reliable and att and att in team_map:
                if team_map[att] == 2:
                    t_open_k += 1
                elif team_map[att] == 3:
                    ct_open_k += 1
        if _is_player(vic, first["victim_name"], player_sid, player_name, nickname):
            opening_deaths += 1
            round_impacts[rnd] -= 3
            if side_reliable and vic and vic in team_map:
                if team_map[vic] == 2:
                    t_open_d += 1
                elif team_map[vic] == 3:
                    ct_open_d += 1

        teammate_death_events: list[tuple[int, int | None]] = []

        for d in sorted_deaths:
            att_sid = d["attacker_steamid"]
            vic_sid = d["victim_steamid"]
            tick = d["tick"]

            if team_state_reliable and vic_sid and vic_sid in team_map:
                team_deaths_in_round[team_map[vic_sid]] += 1

            # teammate death (for trade)
            if (
                team_map and vic_sid and vic_sid in team_map
                and player_team is not None
                and team_map[vic_sid] == player_team
                and not _is_player(vic_sid, d["victim_name"], player_sid, player_name, nickname)
            ):
                teammate_death_events.append((tick, att_sid))

            if _is_player(att_sid, d["attacker_name"], player_sid, player_name, nickname):
                player_kills.append((rnd, tick))
                round_impacts[rnd] += 1
                # trade kill check
                for td_tick, td_killer in teammate_death_events:
                    if td_killer == vic_sid and tick - td_tick <= TRADE_WINDOW_TICKS and tick >= td_tick:
                        trade_kills += 1
                        trade_times.append(tick - td_tick)
                        round_impacts[rnd] += 2
                        break

            if _is_player(vic_sid, d["victim_name"], player_sid, player_name, nickname):
                player_deaths.append((rnd, tick, att_sid))
                killer = att_sid
                traded = False
                if killer and team_map and player_team is not None:
                    for d2 in sorted_deaths:
                        if d2["tick"] <= tick:
                            continue
                        if d2["tick"] - tick > TRADE_WINDOW_TICKS:
                            break
                        a2 = d2["attacker_steamid"]
                        v2 = d2["victim_steamid"]
                        if (
                            a2 and v2 == killer
                            and a2 in team_map
                            and team_map[a2] == player_team
                            and not _is_player(a2, d2["attacker_name"], player_sid, player_name, nickname)
                        ):
                            traded = True
                            traded_deaths += 1
                            break
                if not traded:
                    untraded_deaths += 1
                    round_impacts[rnd] -= 2

                start = round_start_tick(rnd)
                if tick - start <= EARLY_DEATH_TICKS:
                    early_deaths += 1
                    round_impacts[rnd] -= 1

                if team_state_reliable and player_team is not None and vic_sid:
                    pt_deaths = team_deaths_in_round.get(player_team, 0)
                    enemy_teams = [t for t in team_deaths_in_round if t != player_team]
                    enemy_deaths = sum(team_deaths_in_round.get(t, 0) for t in enemy_teams)
                    p_alive = max(0, 5 - pt_deaths)
                    e_alive = max(0, 5 - enemy_deaths)
                    if p_alive > e_alive:
                        deaths_advantage += 1
                    elif p_alive < e_alive:
                        deaths_disadvantage += 1
                    else:
                        deaths_even += 1

    total_deaths = len(player_deaths)
    total_kills = len(player_kills)

    for kr, kt in player_kills:
        died_5 = died_10 = False
        for dr, dt, _ in player_deaths:
            if dr == kr and dt > kt:
                delta = dt - kt
                if delta <= TRADE_WINDOW_TICKS:
                    died_5 = True
                    death_after_kill_5s += 1
                    for r in (kr,):
                        round_impacts[r] -= 1
                if delta <= 10 * TICK_RATE:
                    died_10 = True
                break
        if not died_5:
            kills_with_survival_5s += 1
        if not died_10:
            kills_with_survival_10s += 1

    opening_attempts = opening_kills + opening_deaths
    opening_success = _pct(opening_kills, opening_attempts)
    opening_attempt_rate = _pct(opening_attempts, rounds_analyzed) if rounds_analyzed else None

    trade_kill_rate = _pct(trade_kills, total_kills)
    untraded_pct = _pct(untraded_deaths, total_deaths)
    traded_pct = _pct(traded_deaths, total_deaths)

    early_pct = _pct(early_deaths, total_deaths)
    dak5_pct = _pct(death_after_kill_5s, total_kills) if total_kills else None
    dak10_pct = _pct(death_after_kill_10s, total_kills) if total_kills else None
    surv5 = _pct(kills_with_survival_5s, total_kills)
    surv10 = _pct(kills_with_survival_10s, total_kills)

    avg_trade_time = (
        round(sum(trade_times) / len(trade_times) / TICK_RATE, 2)
        if trade_times else None
    )

    impact_total = sum(round_impacts.values())
    per_round = round(impact_total / rounds_analyzed, 2) if rounds_analyzed else None
    pos_rounds = sum(1 for v in round_impacts.values() if v > 0)
    neg_rounds = sum(1 for v in round_impacts.values() if v < 0)
    neu_rounds = rounds_analyzed - pos_rounds - neg_rounds

    # impact_rating 0-100 from per_round normalized (-5..+5 rough)
    impact_rating = None
    if per_round is not None:
        impact_rating = max(0, min(100, int(50 + per_round * 8)))

    confidence = "none"
    if total_deaths + total_kills >= 5:
        confidence = "low"
    if total_deaths + total_kills >= 15 and player_steamid:
        confidence = "medium"
    if not team_map:
        confidence = "low"

    reliable = (total_deaths + total_kills) >= 10 and player_steamid is not None

    metrics: dict[str, Any] = {
        "reliable": reliable,
        "metrics_confidence": confidence if reliable else "none",
        "source": "Uploaded Demo",
        "rounds_analyzed": rounds_analyzed,
        "opening_kills": opening_kills,
        "opening_deaths": opening_deaths,
        "opening_duel_attempts": opening_attempts,
        "opening_duel_success_pct": opening_success,
        "opening_duel_attempt_rate": opening_attempt_rate,
        "t_opening_kills": t_open_k if side_reliable else "unavailable",
        "t_opening_deaths": t_open_d if side_reliable else "unavailable",
        "ct_opening_kills": ct_open_k if side_reliable else "unavailable",
        "ct_opening_deaths": ct_open_d if side_reliable else "unavailable",
        "trade_kills": trade_kills,
        "traded_deaths": traded_deaths,
        "untraded_deaths": untraded_deaths,
        "trade_kill_rate": trade_kill_rate,
        "traded_death_pct": traded_pct,
        "untraded_death_pct": untraded_pct,
        "average_trade_time": avg_trade_time,
        "total_deaths": total_deaths,
        "total_kills": total_kills,
        "early_deaths": early_deaths,
        "early_death_pct": early_pct,
        "death_after_kill_within_5s": death_after_kill_5s,
        "death_after_kill_within_10s": death_after_kill_10s,
        "death_after_kill_within_5s_pct": dak5_pct,
        "death_after_kill_within_10s_pct": dak10_pct,
        "post_kill_survival_rate_5s": surv5,
        "post_kill_survival_rate_10s": surv10,
        "deaths_when_team_advantage": deaths_advantage if team_state_reliable else "unavailable",
        "deaths_when_team_disadvantage": deaths_disadvantage if team_state_reliable else "unavailable",
        "deaths_when_even": deaths_even if team_state_reliable else "unavailable",
        "round_impact_score_total": impact_total,
        "round_impact_score_per_round": per_round,
        "positive_impact_rounds": pos_rounds,
        "negative_impact_rounds": neg_rounds,
        "neutral_rounds": neu_rounds,
        "impact_rating_0_100": impact_rating,
        "unavailable_reasons": unavailable,
    }
    metrics["unnecessary_death_score"] = compute_unnecessary_death_score(metrics)
    metrics["commentary"] = (
        generate_death_quality_commentary(metrics)
        + generate_opening_commentary(metrics)
        + generate_trade_commentary(metrics)
    )
    return metrics


def analyze_impact_from_parser(
    parser: Any,
    nickname: str,
    matched_name: str | None,
    matched_steamid: int | None,
) -> dict[str, Any]:
    if not demoparser_available():
        return _empty_impact(reason="demoparser2 kurulu değil.")

    try:
        events = parser.list_game_events()
    except Exception as exc:
        return _empty_impact(reason=f"Event listesi okunamadı: {exc}")

    if "player_death" not in events:
        return _empty_impact(reason="player_death eventi yok.")

    try:
        death_df = parser.parse_event(
            "player_death",
            player=["X", "Y", "name", "steamid", "team_number"],
            other=[
                "weapon", "total_rounds_played", "attacker_name", "attacker_steamid",
                "tick", "assister_name", "assister_steamid",
            ],
        )
    except Exception as exc:
        return _empty_impact(reason=f"player_death parse hatası: {exc}")

    deaths = _parse_death_rows(death_df)
    player_info = parser.parse_player_info()
    team_map = _build_team_map(player_info)
    round_starts = _parse_round_starts(parser, events)

    debug_samples = {
        "death_columns": list(death_df.columns) if hasattr(death_df, "columns") else [],
        "death_sample": deaths[:5],
        "round_starts": dict(list(round_starts.items())[:5]),
        "team_map_size": len(team_map),
        "events_sample": [e for e in events if "round" in e.lower() or "death" in e.lower()][:15],
    }

    metrics = analyze_death_events(
        deaths,
        player_steamid=matched_steamid,
        player_name=matched_name or nickname,
        nickname=nickname,
        team_map=team_map,
        round_starts=round_starts,
    )
    metrics["debug"] = debug_samples
    metrics["trade_samples"] = deaths[:3]
    return metrics


def combine_impact_metrics(demo_impacts: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [m for m in demo_impacts if m and m.get("reliable")]
    if not valid:
        reasons = []
        for m in demo_impacts:
            if m and m.get("reason"):
                reasons.append(m["reason"])
        return _empty_impact(
            reason=reasons[0] if reasons else "Impact metrikleri hesaplanamadı.",
        )

    sum_keys = [
        "opening_kills", "opening_deaths", "opening_duel_attempts",
        "trade_kills", "traded_deaths", "untraded_deaths", "total_kills",
        "total_deaths", "early_deaths", "death_after_kill_within_5s",
        "death_after_kill_within_10s",
        "round_impact_score_total", "positive_impact_rounds",
        "negative_impact_rounds", "neutral_rounds", "rounds_analyzed",
        "deaths_when_team_advantage", "deaths_when_team_disadvantage", "deaths_when_even",
    ]
    combined: dict[str, Any] = {"reliable": True, "source": "Uploaded Demo", "demo_count": len(valid)}
    for key in sum_keys:
        total = 0
        for m in valid:
            v = m.get(key)
            if isinstance(v, (int, float)) and v != "unavailable":
                total += int(v)
        combined[key] = total

    combined["opening_duel_success_pct"] = _pct(
        combined["opening_kills"], combined["opening_duel_attempts"],
    )
    combined["opening_duel_attempt_rate"] = _pct(
        combined["opening_duel_attempts"], combined["rounds_analyzed"],
    )
    combined["untraded_death_pct"] = _pct(combined["untraded_deaths"], combined["total_deaths"])
    combined["traded_death_pct"] = _pct(combined["traded_deaths"], combined["total_deaths"])
    combined["early_death_pct"] = _pct(combined["early_deaths"], combined["total_deaths"])
    tk = sum(m.get("opening_kills", 0) + m.get("trade_kills", 0) for m in valid)
    combined["trade_kill_rate"] = _pct(combined["trade_kills"], combined.get("total_kills", 0))

    surv5_num = surv5_den = 0.0
    for m in valid:
        s5 = m.get("post_kill_survival_rate_5s")
        ok = (m.get("opening_kills") or 0) + (m.get("trade_kills") or 0)
        if isinstance(s5, (int, float)) and ok > 0:
            surv5_num += float(s5) * ok / 100.0
            surv5_den += ok
    combined["post_kill_survival_rate_5s"] = (
        round(surv5_num / surv5_den * 100, 1) if surv5_den else None
    )

    dak5_vals = [m.get("death_after_kill_within_5s_pct") for m in valid if isinstance(m.get("death_after_kill_within_5s_pct"), (int, float))]
    combined["death_after_kill_within_5s_pct"] = (
        round(sum(dak5_vals) / len(dak5_vals), 1) if dak5_vals else None
    )

    combined["round_impact_score_per_round"] = (
        round(combined["round_impact_score_total"] / combined["rounds_analyzed"], 2)
        if combined["rounds_analyzed"] else None
    )
    ratings = [m.get("impact_rating_0_100") for m in valid if isinstance(m.get("impact_rating_0_100"), (int, float))]
    combined["impact_rating_0_100"] = int(sum(ratings) / len(ratings)) if ratings else None

    combined["metrics_confidence"] = "medium" if len(valid) >= 2 else valid[0].get("metrics_confidence", "low")
    combined["unnecessary_death_score"] = compute_unnecessary_death_score(combined)
    combined["commentary"] = (
        generate_death_quality_commentary(combined)
        + generate_opening_commentary(combined)
        + generate_trade_commentary(combined)
    )
    combined["t_opening_kills"] = "unavailable"
    combined["ct_opening_kills"] = "unavailable"
    return combined


def render_impact_debug_markdown(debug: dict[str, Any], nickname: str) -> str:
    lines = [
        f"# Impact / Death Quality Debug — {nickname}",
        "",
        "## Parser events",
        "",
    ]
    for e in debug.get("events_sample") or []:
        lines.append(f"- {e}")
    lines.extend([
        "",
        "## Death columns",
        "",
        f"`{', '.join(debug.get('death_columns') or [])}`",
        "",
        "## Death samples",
        "",
    ])
    for row in debug.get("death_sample") or []:
        lines.append(f"- tick={row.get('tick')} round={row.get('round')} "
                     f"att={row.get('attacker_name')} vic={row.get('victim_name')}")
    lines.extend([
        "",
        "## Round starts (sample)",
        "",
        str(debug.get("round_starts") or {}),
        "",
        f"Team map size: {debug.get('team_map_size', 0)}",
        "",
        "## Unavailable reasons",
        "",
    ])
    for r in debug.get("unavailable_reasons") or []:
        lines.append(f"- {r}")
    lines.append("")
    return "\n".join(lines)


def write_impact_debug_report(path: Path, impact: dict[str, Any], nickname: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    dbg = impact.get("debug") or {}
    dbg["unavailable_reasons"] = impact.get("unavailable_reasons") or []
    path.write_text(render_impact_debug_markdown(dbg, nickname), encoding="utf-8")
    return path
