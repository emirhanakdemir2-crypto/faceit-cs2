"""Player geometry visibility candidates + spotted agreement diagnostics.

Diagnostic-only: does not alter Proper Counter-Strafe V2 headline pools or
legacy moving-first-bullet metrics. Never emits measurement_quality=validated.
"""

from __future__ import annotations

import math
from typing import Any

from src import suite_config as cfg
from src.geometry_visibility import GeometryVisibilityBackend, UNAVAILABLE, setup_command

# Team numbers in CS2 demos: 2 = T, 3 = CT (typically).
_PLAYABLE_TEAMS = {2, 3}


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _truthy(value: Any) -> bool | None:
    if value is None or value is UNAVAILABLE:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            return None
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "1", "yes"):
            return True
        if low in ("false", "0", "no"):
            return False
    return None


def _steamid_str(value: Any) -> str | None:
    if value is None or value is UNAVAILABLE:
        return None
    text = str(value).strip()
    return text or None


def _is_alive(row: dict[str, Any]) -> bool:
    alive = _truthy(row.get("is_alive"))
    if alive is False:
        return False
    health = _finite(row.get("health"))
    if health is not None and health <= 0:
        return False
    life_state = _finite(row.get("life_state"))
    if life_state is not None and life_state != 0:
        return False
    if alive is True:
        return True
    # If alive flags missing, do not invent aliveness.
    return False


def _is_crouched(row: dict[str, Any]) -> bool:
    ducked = _truthy(row.get("ducked"))
    ducking = _truthy(row.get("ducking"))
    return bool(ducked or ducking)


def approx_eye_position(row: dict[str, Any]) -> tuple[tuple[float, float, float] | str, str]:
    """Return approximate eye XYZ or UNAVAILABLE; never invent missing XYZ."""
    x = _finite(row.get("X"))
    y = _finite(row.get("Y"))
    z = _finite(row.get("Z"))
    if x is None or y is None or z is None:
        return UNAVAILABLE, "missing_xyz"
    height = (
        cfg.GEOMETRY_APPROX_EYE_HEIGHT_CROUCHED
        if _is_crouched(row)
        else cfg.GEOMETRY_APPROX_EYE_HEIGHT_STANDING
    )
    return (x, y, z + height), cfg.GEOMETRY_EYE_HEIGHT_SOURCE


def _forward_vector(pitch_deg: float, yaw_deg: float) -> tuple[float, float, float]:
    pitch = math.radians(pitch_deg)
    yaw = math.radians(yaw_deg)
    cp = math.cos(pitch)
    return (cp * math.cos(yaw), cp * math.sin(yaw), -math.sin(pitch))


def _angle_deg_between(a: tuple[float, float, float], b: tuple[float, float, float]) -> float | None:
    ax, ay, az = a
    bx, by, bz = b
    na = math.sqrt(ax * ax + ay * ay + az * az)
    nb = math.sqrt(bx * bx + by * by + bz * bz)
    if na <= 0 or nb <= 0:
        return None
    dot = (ax * bx + ay * by + az * bz) / (na * nb)
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))


def resolve_fov_degrees(row: dict[str, Any]) -> dict[str, Any]:
    """Demo fov is often 0/unusable — fall back to config approximate FOV."""
    raw = _finite(row.get("fov"))
    if raw is not None and raw > 1.0:
        return {
            "fov_deg": raw,
            "fov_source": "demo_fov_field",
            "fov_quality": "demo",
            "definitive_fov": True,
        }
    return {
        "fov_deg": cfg.GEOMETRY_APPROX_HORIZONTAL_FOV_DEG,
        "fov_source": cfg.GEOMETRY_FOV_SOURCE,
        "fov_quality": cfg.GEOMETRY_QUALITY_APPROXIMATE,
        "definitive_fov": False,
        "demo_fov_raw": raw if raw is not None else UNAVAILABLE,
    }


def in_horizontal_fov(
    *,
    eye: tuple[float, float, float],
    pitch: float,
    yaw: float,
    target_eye: tuple[float, float, float],
    fov_deg: float,
) -> bool | None:
    forward = _forward_vector(pitch, yaw)
    direction = (
        target_eye[0] - eye[0],
        target_eye[1] - eye[1],
        target_eye[2] - eye[2],
    )
    angle = _angle_deg_between(forward, direction)
    if angle is None:
        return None
    return angle <= (fov_deg / 2.0)


def _spotted_enemy_steamids(shooter_row: dict[str, Any], frame_by_steamid: dict[str, dict]) -> set[str]:
    raw = shooter_row.get("approximate_spotted_by")
    spotted: set[str] = set()
    if not isinstance(raw, (list, tuple, set)):
        return spotted
    shooter_team = _finite(shooter_row.get("team_num"))
    for item in raw:
        sid = _steamid_str(item)
        if not sid:
            continue
        other = frame_by_steamid.get(sid)
        if other is None:
            continue
        other_team = _finite(other.get("team_num"))
        if (
            shooter_team is not None
            and other_team is not None
            and shooter_team in _PLAYABLE_TEAMS
            and other_team in _PLAYABLE_TEAMS
            and other_team != shooter_team
        ):
            spotted.add(sid)
    return spotted


def evaluate_shot_visibility(
    *,
    map_name: str | None,
    shooter_row: dict[str, Any],
    frame_rows: list[dict[str, Any]],
    backend: GeometryVisibilityBackend,
    require_definitive_eye_fov: bool = False,
) -> dict[str, Any]:
    """Geometry+FOV candidate visibility for one shooter frame.

    Never sets definitive enemy_visible=True when eye/FOV are approximate.
    Does not invent a unique target when multiple enemies are visible.
    """
    fov_info = resolve_fov_degrees(shooter_row)
    eye, eye_source = approx_eye_position(shooter_row)
    pitch = _finite(shooter_row.get("pitch"))
    yaw = _finite(shooter_row.get("yaw"))
    shooter_sid = _steamid_str(shooter_row.get("steamid"))
    shooter_team = _finite(shooter_row.get("team_num"))

    base = {
        "measurement_quality": cfg.GEOMETRY_MEASUREMENT_QUALITY,
        "eye_height_source": eye_source,
        "fov_source": fov_info["fov_source"],
        "fov_deg": fov_info["fov_deg"],
        "fov_quality": fov_info["fov_quality"],
        "visibility_quality": cfg.GEOMETRY_QUALITY_APPROXIMATE,
        "enemy_visible": UNAVAILABLE,
        "geometry_any_clear": UNAVAILABLE,
        "visible_enemy_count": 0,
        "visible_enemy_steamids": [],
        "target_steamid": UNAVAILABLE,
        "setup_command": setup_command(),
        "backend_status": UNAVAILABLE,
    }

    if eye is UNAVAILABLE or pitch is None or yaw is None or shooter_sid is None:
        base["unavailable_reason"] = "missing shooter pose"
        return base
    if shooter_team is None or shooter_team not in _PLAYABLE_TEAMS:
        base["unavailable_reason"] = "shooter team unavailable"
        return base

    if require_definitive_eye_fov and (
        eye_source != "demo_eye_offset" or not fov_info.get("definitive_fov")
    ):
        base["unavailable_reason"] = "definitive eye/FOV unavailable"
        return base

    # Approximate path always in V1 — demo lacks real eye offset / usable FOV.
    # Never emit definitive enemy_visible or validated quality in this layer.
    base["visibility_quality"] = cfg.GEOMETRY_QUALITY_APPROXIMATE
    base["enemy_visible"] = UNAVAILABLE

    frame_by_sid = {
        sid: row
        for row in frame_rows
        if (sid := _steamid_str(row.get("steamid"))) is not None
    }
    spotted_enemies = _spotted_enemy_steamids(shooter_row, frame_by_sid)

    visible_ids: list[str] = []
    geometry_clear_any = False
    backend_status = cfg.GEOMETRY_STATUS_AVAILABLE
    los_checked = 0

    for sid, row in frame_by_sid.items():
        if sid == shooter_sid:
            continue
        team = _finite(row.get("team_num"))
        if team is None or team not in _PLAYABLE_TEAMS or team == shooter_team:
            continue  # teammates / invalid never count as enemies
        if not _is_alive(row):
            continue

        target_eye, _ = approx_eye_position(row)
        if target_eye is UNAVAILABLE:
            continue

        los = backend.is_visible(map_name, eye, target_eye)  # type: ignore[arg-type]
        backend_status = str(los.get("status") or backend_status)
        if los.get("status") != cfg.GEOMETRY_STATUS_AVAILABLE:
            base["backend_status"] = backend_status
            base["setup_command"] = los.get("setup_command") or setup_command()
            base["unavailable_reason"] = los.get("error") or backend_status
            base["geometry_any_clear"] = UNAVAILABLE
            return base

        los_checked += 1
        if los.get("visible") is True:
            geometry_clear_any = True
            in_fov = in_horizontal_fov(
                eye=eye,  # type: ignore[arg-type]
                pitch=pitch,
                yaw=yaw,
                target_eye=target_eye,  # type: ignore[arg-type]
                fov_deg=float(fov_info["fov_deg"]),
            )
            if in_fov is True:
                visible_ids.append(sid)

    base["backend_status"] = backend_status
    base["geometry_any_clear"] = geometry_clear_any
    base["los_checked"] = los_checked
    base["visible_enemy_count"] = len(visible_ids)
    base["visible_enemy_steamids"] = visible_ids
    base["spotted_enemy_count"] = len(spotted_enemies)
    base["spotted_enemy_steamids"] = sorted(spotted_enemies)
    base["spotted_any"] = bool(spotted_enemies)
    base["approx_enemy_in_view"] = len(visible_ids) > 0

    if len(visible_ids) == 1:
        base["target_steamid"] = visible_ids[0]
    else:
        base["target_steamid"] = UNAVAILABLE

    geometry_visible = len(visible_ids) > 0
    spotted_any = bool(spotted_enemies)
    if geometry_visible and spotted_any:
        bucket = cfg.GEOMETRY_AGREEMENT_VISIBLE_SPOTTED
    elif geometry_visible and not spotted_any:
        bucket = cfg.GEOMETRY_AGREEMENT_VISIBLE_NOT_SPOTTED
    elif (not geometry_visible) and spotted_any:
        bucket = cfg.GEOMETRY_AGREEMENT_BLOCKED_SPOTTED
    else:
        bucket = cfg.GEOMETRY_AGREEMENT_BLOCKED_NOT_SPOTTED
    base["agreement_bucket"] = bucket
    base["geometry_visible_candidate"] = geometry_visible
    return base


def _empty_agreement(*, reason: str, map_name: str | None = None) -> dict[str, Any]:
    return {
        "status": "Unavailable",
        "measurement_quality": cfg.GEOMETRY_MEASUREMENT_QUALITY,
        "map_name": map_name or UNAVAILABLE,
        "shot_ticks_analyzed": 0,
        "geometry_resolved_count": 0,
        "unavailable_count": 0,
        "agreement_pct": UNAVAILABLE,
        "disagreement_pct": UNAVAILABLE,
        "mean_visible_enemy_count": UNAVAILABLE,
        "buckets": {
            cfg.GEOMETRY_AGREEMENT_VISIBLE_SPOTTED: 0,
            cfg.GEOMETRY_AGREEMENT_VISIBLE_NOT_SPOTTED: 0,
            cfg.GEOMETRY_AGREEMENT_BLOCKED_SPOTTED: 0,
            cfg.GEOMETRY_AGREEMENT_BLOCKED_NOT_SPOTTED: 0,
        },
        "by_map": {},
        "eye_height_source": cfg.GEOMETRY_EYE_HEIGHT_SOURCE,
        "fov_source": cfg.GEOMETRY_FOV_SOURCE,
        "backend_source": cfg.GEOMETRY_BACKEND_SOURCE,
        "backend_version": cfg.GEOMETRY_BACKEND_VERSION_PIN,
        "setup_command": setup_command(),
        "unavailable_reason": reason,
        "coach_note": "geometry LoS diagnostic only; not a definitive visibility verdict",
    }


def compute_visibility_agreement(
    *,
    map_name: str | None,
    shooter_steamid: str,
    shot_ticks: list[int],
    tick_rows: list[dict[str, Any]],
    backend: GeometryVisibilityBackend | None = None,
) -> dict[str, Any]:
    """Compare approximate geometry visibility vs approximate_spotted_by."""
    backend = backend or GeometryVisibilityBackend()
    if not shot_ticks:
        return _empty_agreement(reason="no shot ticks", map_name=map_name)

    status = backend.ensure_map(map_name)
    if status.get("status") != cfg.GEOMETRY_STATUS_AVAILABLE:
        out = _empty_agreement(
            reason=str(status.get("error") or status.get("status")),
            map_name=map_name,
        )
        out["backend_status"] = status.get("status")
        out["setup_command"] = status.get("setup_command") or setup_command()
        out["status"] = status.get("status")
        return out

    by_tick: dict[int, list[dict[str, Any]]] = {}
    for row in tick_rows:
        tick = row.get("tick")
        try:
            t = int(tick)
        except (TypeError, ValueError):
            continue
        by_tick.setdefault(t, []).append(row)

    buckets = {
        cfg.GEOMETRY_AGREEMENT_VISIBLE_SPOTTED: 0,
        cfg.GEOMETRY_AGREEMENT_VISIBLE_NOT_SPOTTED: 0,
        cfg.GEOMETRY_AGREEMENT_BLOCKED_SPOTTED: 0,
        cfg.GEOMETRY_AGREEMENT_BLOCKED_NOT_SPOTTED: 0,
    }
    resolved = 0
    unavailable = 0
    visible_counts: list[int] = []
    analyzed = 0

    # Deterministic: process shot ticks in ascending order, preserve duplicates
    # as separate analyzed shots (same as prior H4 behavior on input order...
    # H4 iterated shot_ticks as provided from shot_rows order). Keep input order.
    for tick in shot_ticks:
        frame = by_tick.get(int(tick)) or []
        if not frame:
            unavailable += 1
            continue
        shooter_row = None
        for row in frame:
            if _steamid_str(row.get("steamid")) == str(shooter_steamid):
                shooter_row = row
                break
        if shooter_row is None:
            unavailable += 1
            continue
        analyzed += 1
        result = evaluate_shot_visibility(
            map_name=map_name,
            shooter_row=shooter_row,
            frame_rows=frame,
            backend=backend,
        )
        if result.get("agreement_bucket") in buckets and result.get("geometry_any_clear") is not UNAVAILABLE:
            buckets[str(result["agreement_bucket"])] += 1
            resolved += 1
            visible_counts.append(int(result.get("visible_enemy_count") or 0))
        else:
            unavailable += 1

    agree = (
        buckets[cfg.GEOMETRY_AGREEMENT_VISIBLE_SPOTTED]
        + buckets[cfg.GEOMETRY_AGREEMENT_BLOCKED_NOT_SPOTTED]
    )
    disagree = (
        buckets[cfg.GEOMETRY_AGREEMENT_VISIBLE_NOT_SPOTTED]
        + buckets[cfg.GEOMETRY_AGREEMENT_BLOCKED_SPOTTED]
    )
    if resolved <= 0:
        agreement_pct: float | str = UNAVAILABLE
        disagreement_pct: float | str = UNAVAILABLE
        mean_vis: float | str = UNAVAILABLE
    else:
        agreement_pct = round(100.0 * agree / resolved, 1)
        disagreement_pct = round(100.0 * disagree / resolved, 1)
        mean_vis = round(sum(visible_counts) / len(visible_counts), 3) if visible_counts else UNAVAILABLE

    map_key = str(status.get("map_name") or map_name or UNAVAILABLE)
    return {
        "status": cfg.GEOMETRY_STATUS_AVAILABLE,
        "measurement_quality": cfg.GEOMETRY_MEASUREMENT_QUALITY,
        "map_name": map_key,
        "shot_ticks_analyzed": analyzed,
        "geometry_resolved_count": resolved,
        "unavailable_count": unavailable,
        "agreement_pct": agreement_pct,
        "disagreement_pct": disagreement_pct,
        "mean_visible_enemy_count": mean_vis,
        "buckets": buckets,
        "by_map": {
            map_key: {
                "resolved": resolved,
                "agreement_pct": agreement_pct,
                "disagreement_pct": disagreement_pct,
                "buckets": dict(buckets),
            },
        },
        "eye_height_source": cfg.GEOMETRY_EYE_HEIGHT_SOURCE,
        "fov_source": cfg.GEOMETRY_FOV_SOURCE,
        "backend_source": backend.backend_source,
        "backend_version": backend.backend_version,
        "backend_create_counts": backend.create_counts,
        "setup_command": setup_command(),
        "unavailable_reason": UNAVAILABLE,
        "coach_note": "geometry LoS diagnostic only; not a definitive visibility verdict",
    }


def combine_visibility_agreement(demo_results: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [r for r in demo_results if isinstance(r, dict) and r]
    if not usable:
        return _empty_agreement(reason="no demo visibility results")

    buckets = {
        cfg.GEOMETRY_AGREEMENT_VISIBLE_SPOTTED: 0,
        cfg.GEOMETRY_AGREEMENT_VISIBLE_NOT_SPOTTED: 0,
        cfg.GEOMETRY_AGREEMENT_BLOCKED_SPOTTED: 0,
        cfg.GEOMETRY_AGREEMENT_BLOCKED_NOT_SPOTTED: 0,
    }
    analyzed = resolved = unavailable = 0
    vis_sum = 0.0
    vis_n = 0
    by_map: dict[str, Any] = {}

    for r in usable:
        analyzed += int(r.get("shot_ticks_analyzed") or 0)
        resolved += int(r.get("geometry_resolved_count") or 0)
        unavailable += int(r.get("unavailable_count") or 0)
        b = r.get("buckets") or {}
        for key in buckets:
            buckets[key] += int(b.get(key) or 0)
        mean = r.get("mean_visible_enemy_count")
        n = int(r.get("geometry_resolved_count") or 0)
        if n > 0 and isinstance(mean, (int, float)):
            vis_sum += float(mean) * n
            vis_n += n
        for mp, payload in (r.get("by_map") or {}).items():
            slot = by_map.setdefault(
                mp,
                {
                    "resolved": 0,
                    "buckets": {k: 0 for k in buckets},
                },
            )
            slot["resolved"] += int(payload.get("resolved") or 0)
            pb = payload.get("buckets") or {}
            for key in buckets:
                slot["buckets"][key] += int(pb.get(key) or 0)

    agree = (
        buckets[cfg.GEOMETRY_AGREEMENT_VISIBLE_SPOTTED]
        + buckets[cfg.GEOMETRY_AGREEMENT_BLOCKED_NOT_SPOTTED]
    )
    disagree = (
        buckets[cfg.GEOMETRY_AGREEMENT_VISIBLE_NOT_SPOTTED]
        + buckets[cfg.GEOMETRY_AGREEMENT_BLOCKED_SPOTTED]
    )
    if resolved <= 0:
        return _empty_agreement(reason="no resolved geometry samples")

    for mp, slot in by_map.items():
        r_n = int(slot["resolved"] or 0)
        b = slot["buckets"]
        a = b[cfg.GEOMETRY_AGREEMENT_VISIBLE_SPOTTED] + b[cfg.GEOMETRY_AGREEMENT_BLOCKED_NOT_SPOTTED]
        d = b[cfg.GEOMETRY_AGREEMENT_VISIBLE_NOT_SPOTTED] + b[cfg.GEOMETRY_AGREEMENT_BLOCKED_SPOTTED]
        slot["agreement_pct"] = round(100.0 * a / r_n, 1) if r_n else UNAVAILABLE
        slot["disagreement_pct"] = round(100.0 * d / r_n, 1) if r_n else UNAVAILABLE

    return {
        "status": cfg.GEOMETRY_STATUS_AVAILABLE,
        "measurement_quality": cfg.GEOMETRY_MEASUREMENT_QUALITY,
        "map_name": UNAVAILABLE,
        "shot_ticks_analyzed": analyzed,
        "geometry_resolved_count": resolved,
        "unavailable_count": unavailable,
        "agreement_pct": round(100.0 * agree / resolved, 1),
        "disagreement_pct": round(100.0 * disagree / resolved, 1),
        "mean_visible_enemy_count": round(vis_sum / vis_n, 3) if vis_n else UNAVAILABLE,
        "buckets": buckets,
        "by_map": by_map,
        "eye_height_source": cfg.GEOMETRY_EYE_HEIGHT_SOURCE,
        "fov_source": cfg.GEOMETRY_FOV_SOURCE,
        "backend_source": cfg.GEOMETRY_BACKEND_SOURCE,
        "backend_version": cfg.GEOMETRY_BACKEND_VERSION_PIN,
        "setup_command": setup_command(),
        "unavailable_reason": UNAVAILABLE,
        "coach_note": "geometry LoS diagnostic only; not a definitive visibility verdict",
        "demo_count": len(usable),
    }
