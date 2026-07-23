"""Duel / shot context builder from verified demo fields only.

Does not invent targets for miss shots. Spotted engagement uses
`approximate_spotted_by` (list of observer steamids) when resolvable.
"""

from __future__ import annotations

import math
from typing import Any

from src import suite_config as cfg
from src.demo_parser import (
    _is_ak_weapon,
    _is_m4_weapon,
    _is_rifle_weapon,
    _tick_int,
    _weapon_base,
)

UNAVAILABLE = "Unavailable"


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _as_steamid(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text or text in {"0", "None", "nan"}:
        return None
    return text


def _as_steamid_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            sid = _as_steamid(item)
            if sid:
                out.append(sid)
        return out
    sid = _as_steamid(value)
    return [sid] if sid else []


def _truthy_crouch(ducked: Any, ducking: Any) -> bool | None:
    if ducked is None and ducking is None:
        return None
    return bool(ducked) or bool(ducking)


def _speed_ratio(velocity: Any, max_speed: Any) -> float | None:
    vel = _finite_number(velocity)
    mx = _finite_number(max_speed)
    if vel is None or mx is None:
        return None
    if mx <= 0:
        return None
    ratio = vel / mx
    if not math.isfinite(ratio) or ratio < 0:
        return None
    return ratio


def _team_num(value: Any) -> int | None:
    num = _finite_number(value)
    if num is None:
        return None
    return int(num)


def index_tick_rows_by_tick(tick_rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    indexed: dict[int, list[dict[str, Any]]] = {}
    for row in tick_rows:
        tick = _tick_int(row)
        if tick is None:
            continue
        indexed.setdefault(tick, []).append(row)
    return indexed


def nearest_tick_frame(
    tick_index: dict[int, list[dict[str, Any]]],
    tick: int,
    *,
    tolerance: int | None = None,
) -> tuple[int | None, list[dict[str, Any]]]:
    tol = cfg.V2_TICK_MATCH_TOLERANCE if tolerance is None else tolerance
    if tick in tick_index:
        return tick, tick_index[tick]
    best_t: int | None = None
    best_dist: int | None = None
    for candidate in tick_index:
        dist = abs(candidate - tick)
        if dist > tol:
            continue
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_t = candidate
    if best_t is None:
        return None, []
    return best_t, tick_index[best_t]


def resolve_approximate_spotted_enemies(
    shooter_row: dict[str, Any],
    frame_rows: list[dict[str, Any]],
    shooter_steamid: str,
) -> list[dict[str, Any]]:
    """Resolve approximate_spotted_by steamid lists to enemy players in-frame.

    Probe evidence: approximate_spotted_by is a list of steamids of players
    who spot this player (not entity_id bits). Mutual check:
    - enemy steamid appears in shooter's mask, or
    - shooter steamid appears in enemy's mask.
    """
    shooter_team = _team_num(shooter_row.get("team_num"))
    shooter_mask = set(_as_steamid_list(shooter_row.get("approximate_spotted_by")))
    enemies: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in frame_rows:
        other = _as_steamid(row.get("steamid") or row.get("player_steamid"))
        if not other or other == shooter_steamid:
            continue
        other_team = _team_num(row.get("team_num"))
        if shooter_team is not None and other_team is not None and other_team == shooter_team:
            continue
        other_mask = set(_as_steamid_list(row.get("approximate_spotted_by")))
        engaged = other in shooter_mask or shooter_steamid in other_mask
        if not engaged:
            continue
        if other in seen:
            continue
        seen.add(other)
        enemies.append({
            "steamid": other,
            "name": row.get("name"),
            "entity_id": row.get("entity_id"),
            "team_num": other_team,
            "eligibility_source": cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED,
        })
    return enemies


def confirmed_hurt_targets_at_tick(
    hurt_rows: list[dict[str, Any]],
    *,
    shooter_steamid: str,
    tick: int,
    tolerance: int | None = None,
) -> list[dict[str, Any]]:
    """Targets confirmed by player_hurt with shooter as attacker near tick.

    Used only for shots that already have a hurt — never to invent miss targets.
    """
    tol = cfg.V2_TICK_MATCH_TOLERANCE if tolerance is None else tolerance
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in hurt_rows:
        attacker = _as_steamid(row.get("attacker_steamid"))
        victim = _as_steamid(row.get("user_steamid") or row.get("player_steamid"))
        hurt_tick = _tick_int(row)
        if attacker != shooter_steamid or not victim or hurt_tick is None:
            continue
        if abs(hurt_tick - tick) > tol:
            continue
        if victim in seen:
            continue
        seen.add(victim)
        targets.append({
            "steamid": victim,
            "name": row.get("user_name") or row.get("player_name"),
            "eligibility_source": cfg.V2_ELIGIBILITY_SOURCE_HURT,
            "hurt_tick": hurt_tick,
        })
    return targets


def _empty_context(
    *,
    demo_id: str,
    tick: int | None,
    round_num: Any,
    weapon: str | None,
    unavailable_reason: str,
) -> dict[str, Any]:
    return {
        "demo_id": demo_id,
        "round": round_num if round_num is not None else UNAVAILABLE,
        "tick": tick if tick is not None else UNAVAILABLE,
        "player_steamid": UNAVAILABLE,
        "weapon": weapon or UNAVAILABLE,
        "weapon_class": UNAVAILABLE,
        "is_rifle": False,
        "is_ak": False,
        "is_m4": False,
        "shot_index_in_burst": UNAVAILABLE,
        "is_first_bullet": UNAVAILABLE,
        "velocity": UNAVAILABLE,
        "max_speed": UNAVAILABLE,
        "speed_ratio": UNAVAILABLE,
        "crouch": UNAVAILABLE,
        "position": UNAVAILABLE,
        "view_angles": UNAVAILABLE,
        "target_steamid": UNAVAILABLE,
        "target_candidates": [],
        "engagement_verified": False,
        "evidence_bucket": cfg.V2_EVIDENCE_UNRESOLVED,
        "eligibility_source": UNAVAILABLE,
        "confidence": "none",
        "unavailable_reason": unavailable_reason,
    }


def build_shot_contexts(
    *,
    demo_id: str,
    shooter_steamid: str,
    shot_rows: list[dict[str, Any]],
    tick_rows: list[dict[str, Any]],
    hurt_rows: list[dict[str, Any]] | None = None,
    burst_gap_ticks: int = 16,
) -> list[dict[str, Any]]:
    """Build per-shot duel contexts. No invented miss targets."""
    shooter = _as_steamid(shooter_steamid)
    if not shooter:
        return []

    tick_index = index_tick_rows_by_tick(tick_rows)
    hurts = hurt_rows or []
    contexts: list[dict[str, Any]] = []

    prev_tick: int | None = None
    prev_weapon: str | None = None
    burst_index = 0

    for shot in shot_rows:
        tick = _tick_int(shot)
        weapon = shot.get("weapon") or shot.get("weapon_name") or shot.get("active_weapon_name")
        weapon_s = str(weapon) if weapon is not None else None
        round_num = shot.get("total_rounds_played")
        if round_num is None:
            round_num = shot.get("round")

        if tick is None:
            contexts.append(
                _empty_context(
                    demo_id=demo_id,
                    tick=None,
                    round_num=round_num,
                    weapon=weapon_s,
                    unavailable_reason="shot tick missing",
                )
            )
            continue

        if (
            prev_tick is not None
            and prev_weapon == weapon_s
            and (tick - prev_tick) <= burst_gap_ticks
        ):
            burst_index += 1
        else:
            burst_index = 1
        prev_tick = tick
        prev_weapon = weapon_s

        matched_tick, frame = nearest_tick_frame(tick_index, tick)
        shooter_rows = [
            row for row in frame
            if _as_steamid(row.get("steamid") or row.get("player_steamid")) == shooter
        ]
        if not shooter_rows:
            contexts.append(
                _empty_context(
                    demo_id=demo_id,
                    tick=tick,
                    round_num=round_num,
                    weapon=weapon_s,
                    unavailable_reason="shooter tick frame unavailable",
                )
            )
            continue

        srow = shooter_rows[0]
        velocity = _finite_number(srow.get("velocity") if srow.get("velocity") is not None else shot.get("user_velocity"))
        if velocity is None:
            velocity = _finite_number(shot.get("velocity"))
        max_speed = _finite_number(srow.get("max_speed"))
        ratio = _speed_ratio(velocity, max_speed)
        crouch = _truthy_crouch(srow.get("ducked"), srow.get("ducking"))

        pos = UNAVAILABLE
        x = _finite_number(srow.get("X"))
        y = _finite_number(srow.get("Y"))
        z = _finite_number(srow.get("Z"))
        if x is not None and y is not None and z is not None:
            pos = {"x": x, "y": y, "z": z}

        view = UNAVAILABLE
        pitch = _finite_number(srow.get("pitch"))
        yaw = _finite_number(srow.get("yaw"))
        if pitch is not None and yaw is not None:
            view = {"pitch": pitch, "yaw": yaw}

        if round_num is None:
            round_num = srow.get("total_rounds_played")

        spotted_enemies = resolve_approximate_spotted_enemies(srow, frame, shooter)
        hurt_targets = confirmed_hurt_targets_at_tick(
            hurts, shooter_steamid=shooter, tick=tick,
        )

        has_spotted = bool(spotted_enemies)
        has_hurt = bool(hurt_targets)
        if has_spotted and has_hurt:
            evidence_bucket = cfg.V2_EVIDENCE_SPOTTED_AND_HURT
            eligibility_source = cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED
            engagement = True
            candidates = spotted_enemies
            # Prefer single spotted enemy; hurt confirms engagement but does not
            # invent miss targets and does not replace spotted evidence class.
            if len(spotted_enemies) == 1:
                target_steamid = spotted_enemies[0]["steamid"]
            elif len(hurt_targets) == 1:
                target_steamid = hurt_targets[0]["steamid"]
            else:
                target_steamid = UNAVAILABLE
        elif has_spotted:
            evidence_bucket = cfg.V2_EVIDENCE_SPOTTED_ONLY
            eligibility_source = cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED
            engagement = True
            candidates = spotted_enemies
            target_steamid = (
                spotted_enemies[0]["steamid"] if len(spotted_enemies) == 1 else UNAVAILABLE
            )
        elif has_hurt:
            evidence_bucket = cfg.V2_EVIDENCE_HURT_ONLY
            eligibility_source = cfg.V2_ELIGIBILITY_SOURCE_HURT
            engagement = True
            candidates = hurt_targets
            target_steamid = (
                hurt_targets[0]["steamid"] if len(hurt_targets) == 1 else UNAVAILABLE
            )
        else:
            evidence_bucket = cfg.V2_EVIDENCE_UNRESOLVED
            eligibility_source = UNAVAILABLE
            engagement = False
            candidates = []
            target_steamid = UNAVAILABLE

        unavailable_reason = ""
        if max_speed is None:
            unavailable_reason = "max_speed unavailable"
        elif not engagement:
            unavailable_reason = "engagement context unverified"

        contexts.append({
            "demo_id": demo_id,
            "round": round_num if round_num is not None else UNAVAILABLE,
            "tick": tick,
            "matched_tick": matched_tick if matched_tick is not None else UNAVAILABLE,
            "player_steamid": shooter,
            "weapon": weapon_s or UNAVAILABLE,
            "weapon_class": _weapon_base(weapon_s) or UNAVAILABLE,
            "is_rifle": _is_rifle_weapon(weapon_s),
            "is_ak": _is_ak_weapon(weapon_s),
            "is_m4": _is_m4_weapon(weapon_s),
            "shot_index_in_burst": burst_index,
            "is_first_bullet": burst_index == 1,
            "velocity": velocity if velocity is not None else UNAVAILABLE,
            "max_speed": max_speed if max_speed is not None else UNAVAILABLE,
            "speed_ratio": ratio if ratio is not None else UNAVAILABLE,
            "crouch": crouch if crouch is not None else UNAVAILABLE,
            "position": pos,
            "view_angles": view,
            "target_steamid": target_steamid,
            "target_candidates": candidates,
            "engagement_verified": engagement,
            "evidence_bucket": evidence_bucket,
            "eligibility_source": eligibility_source,
            "confidence": "medium" if engagement else "none",
            "unavailable_reason": unavailable_reason or UNAVAILABLE,
        })

    return contexts
