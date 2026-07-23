from __future__ import annotations

import gzip
import math
import re
import shutil
from pathlib import Path
from typing import Any

from src.config import MISSING_DATA_LABEL

DEMO_EXTENSIONS = (".dem", ".dem.gz", ".dem.zst", ".zst", ".gz")
COMPRESSED_EXTENSIONS = (".dem.gz", ".dem.zst", ".zst", ".gz")
MATCH_ID_RE = re.compile(
    r"1-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)
STOPPED_SPEED_THRESHOLD = 5.0
MOVING_SPEED_THRESHOLD = 34.0
MIN_SHOTS_FOR_METRICS = 20
SPRAY_GAP_TICKS = 16
LONG_SPRAY_MIN_SHOTS = 7
HIGH_MOVING_PCT = 50.0
HIGH_FIRST_BULLET_MOVING_PCT = 40.0
HIGH_LONG_SPRAY_PCT = 35.0
NON_GUN_WEAPON_PARTS = (
    "knife", "grenade", "flash", "smoke", "molotov", "incgrenade", "decoy", "c4",
)
RIFLE_WEAPON_PARTS = ("ak47", "m4a1", "m4a4", "aug", "sg556", "galil", "famas")
STARTER_PISTOL_PARTS = ("glock", "usp_silencer", "hkp2000")
FORCE_PISTOL_PARTS = ("tec9", "fiveseven", "p250", "cz75a", "elite")
DEAGLE_PARTS = ("deagle",)
REVOLVER_PARTS = ("revolver",)
SMG_WEAPON_PARTS = ("mp9", "mac10", "mp7", "mp5sd", "ump45", "p90", "bizon")
PISTOL_WEAPON_PARTS = STARTER_PISTOL_PARTS + FORCE_PISTOL_PARTS + DEAGLE_PARTS + REVOLVER_PARTS
MIN_PISTOL_SHOTS_FOR_COMMENTARY = 10


def demoparser_available() -> bool:
    try:
        import demoparser2  # noqa: F401

        return True
    except ImportError:
        return False


def get_demoparser_version() -> str:
    try:
        import demoparser2

        return str(getattr(demoparser2, "__version__", "unknown"))
    except ImportError:
        return "not installed"


def _is_nan(val: Any) -> bool:
    try:
        return val is None or (isinstance(val, float) and math.isnan(val))
    except (TypeError, ValueError):
        return val is None


def _is_gun_weapon(weapon: str | None) -> bool:
    if not weapon:
        return False
    w = weapon.lower()
    return not any(part in w for part in NON_GUN_WEAPON_PARTS)


def _weapon_base(weapon: str | None) -> str:
    if not weapon:
        return ""
    return weapon.lower().replace("weapon_", "")


def _weapon_matches_parts(weapon: str | None, parts: tuple[str, ...]) -> bool:
    w = _weapon_base(weapon)
    return bool(w) and any(part in w for part in parts)


def _is_pistol_weapon(weapon: str | None) -> bool:
    return _weapon_matches_parts(weapon, PISTOL_WEAPON_PARTS)


def _is_starter_pistol_weapon(weapon: str | None) -> bool:
    return _weapon_matches_parts(weapon, STARTER_PISTOL_PARTS)


def _is_force_pistol_weapon(weapon: str | None) -> bool:
    return _weapon_matches_parts(weapon, FORCE_PISTOL_PARTS)


def _is_deagle_weapon(weapon: str | None) -> bool:
    return _weapon_matches_parts(weapon, DEAGLE_PARTS)


def _is_revolver_weapon(weapon: str | None) -> bool:
    return _weapon_matches_parts(weapon, REVOLVER_PARTS)


def _is_smg_weapon(weapon: str | None) -> bool:
    return _weapon_matches_parts(weapon, SMG_WEAPON_PARTS)


def _is_rifle_weapon(weapon: str | None) -> bool:
    if not weapon:
        return False
    w = weapon.lower()
    return any(part in w for part in RIFLE_WEAPON_PARTS)


def _is_ak_weapon(weapon: str | None) -> bool:
    return bool(weapon and "ak47" in weapon.lower())


def _is_m4_weapon(weapon: str | None) -> bool:
    if not weapon:
        return False
    w = weapon.lower()
    return "m4a1" in w or "m4a4" in w


def _row_player_name(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        val = row.get(key)
        if val not in (None, ""):
            return str(val)
    return None


def _row_steamid(row: dict[str, Any]) -> int | None:
    for key in ("user_steamid", "steamid", "attacker_steamid"):
        val = row.get(key)
        if val in (None, ""):
            continue
        try:
            return int(val)
        except (TypeError, ValueError):
            continue
    return None


def _unavailable(reason: str, *, demo_count: int = 0) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": reason,
        "demo_count": demo_count,
        "confidence": "none",
    }


def _df_records(df: Any) -> list[dict[str, Any]]:
    if df is None:
        return []
    try:
        if hasattr(df, "empty") and df.empty:
            return []
        return df.to_dict("records")
    except Exception:
        return []


def _extract_match_id(filename: str) -> str | None:
    match = MATCH_ID_RE.search(filename)
    return match.group(0) if match else None


def _is_native_dem(filename: str) -> bool:
    name = filename.lower()
    if name.endswith(".dem.gz") or name.endswith(".dem.zst"):
        return False
    if name.endswith(".zst") or name.endswith(".gz"):
        return False
    return name.endswith(".dem")


def _decompressed_dem_path(compressed_path: Path) -> Path:
    name = compressed_path.name
    lower = name.lower()
    if lower.endswith(".dem.zst"):
        return compressed_path.with_name(name[:-4])
    if lower.endswith(".dem.gz"):
        return compressed_path.with_name(name[:-3])
    if lower.endswith(".zst"):
        return compressed_path.with_name(f"{name[:-4]}.dem")
    if lower.endswith(".gz") and not lower.endswith(".dem.gz"):
        return compressed_path.with_name(f"{name[:-3]}.dem")
    return compressed_path


def extract_compressed_demo(compressed_path: Path) -> dict[str, Any]:
    """Sıkıştırılmış .dem.zst / .dem.gz / .zst dosyasını aynı klasöre .dem olarak çıkarır."""
    result: dict[str, Any] = {
        "source": compressed_path.name,
        "source_path": str(compressed_path.resolve()),
        "output": "",
        "output_path": "",
        "extracted": False,
        "skipped_existing": False,
        "error": "",
    }

    if not compressed_path.exists():
        result["error"] = "Sıkıştırılmış demo dosyası bulunamadı."
        return result

    out_path = _decompressed_dem_path(compressed_path)
    result["output"] = out_path.name
    result["output_path"] = str(out_path.resolve())

    if out_path.exists():
        result["skipped_existing"] = True
        result["extracted"] = True
        return result

    name_lower = compressed_path.name.lower()
    try:
        if name_lower.endswith(".dem.zst") or name_lower.endswith(".zst"):
            try:
                import zstandard as zstd
            except ImportError:
                result["error"] = "zstandard kurulu değil. pip install zstandard"
                return result
            dctx = zstd.ZstdDecompressor()
            with compressed_path.open("rb") as f_in, out_path.open("wb") as f_out:
                dctx.copy_stream(f_in, f_out)
        elif name_lower.endswith(".dem.gz") or (
            name_lower.endswith(".gz") and not name_lower.endswith(".dem.gz")
        ):
            with gzip.open(compressed_path, "rb") as f_in, out_path.open("wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        else:
            result["error"] = "Desteklenmeyen sıkıştırma formatı."
            return result
        result["extracted"] = True
    except Exception as exc:
        result["error"] = f"Çıkarma hatası: {exc}"
        if out_path.exists():
            try:
                out_path.unlink()
            except OSError:
                pass

    return result


def find_demo_files(demo_folder: Path) -> list[dict[str, Any]]:
    """Demo klasöründeki demo dosyalarını listeler (.dem, .zst, .dem.gz, .dem.zst)."""
    if not demo_folder.exists():
        return []

    files: list[dict[str, Any]] = []
    for path in sorted(demo_folder.iterdir()):
        if not path.is_file():
            continue
        name_lower = path.name.lower()
        if not any(name_lower.endswith(ext) for ext in DEMO_EXTENSIONS):
            continue
        compressed = any(name_lower.endswith(ext) for ext in COMPRESSED_EXTENSIONS)
        files.append({
            "filename": path.name,
            "path": str(path.resolve()),
            "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
            "match_id": _extract_match_id(path.name) or MISSING_DATA_LABEL,
            "compressed": compressed,
            "parseable": _is_native_dem(path.name),
        })
    return files


def prepare_demos_for_parsing(demo_folder: Path) -> dict[str, Any]:
    """Sıkıştırılmış demoları çıkarır ve parse edilebilir .dem listesi üretir."""
    raw_files = find_demo_files(demo_folder)
    extractions: list[dict[str, Any]] = []
    parseable: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for entry in raw_files:
        if not entry.get("parseable"):
            continue
        path = entry["path"]
        if path in seen_paths:
            continue
        seen_paths.add(path)
        parseable.append({**entry, "source_compressed": None, "extraction": None})

    for entry in raw_files:
        if not entry.get("compressed"):
            continue
        extraction = extract_compressed_demo(Path(entry["path"]))
        extractions.append(extraction)
        if not extraction.get("extracted") or extraction.get("error"):
            continue
        out_path = Path(extraction["output_path"])
        if not out_path.exists():
            continue
        out_str = str(out_path.resolve())
        if out_str in seen_paths:
            continue
        seen_paths.add(out_str)
        parseable.append({
            "filename": out_path.name,
            "path": out_str,
            "size_mb": round(out_path.stat().st_size / (1024 * 1024), 2),
            "match_id": _extract_match_id(out_path.name) or MISSING_DATA_LABEL,
            "compressed": False,
            "parseable": True,
            "source_compressed": entry["filename"],
            "extraction": extraction,
        })

    return {
        "files": raw_files,
        "parseable": parseable,
        "extractions": extractions,
        "compressed_found": any(f.get("compressed") for f in raw_files),
    }


def _resolve_player_names(player_info: Any, nickname: str) -> tuple[bool, str | None, int | None, list[str]]:
    nick = nickname.strip().lower()
    all_names: list[str] = []
    matched_name: str | None = None
    matched_steamid: int | None = None

    for row in _df_records(player_info):
        name = _row_player_name(row, "name", "player_name", "playerName")
        if not name:
            continue
        all_names.append(name)
        name_lower = name.lower()
        if nick == name_lower or nick in name_lower or name_lower in nick:
            matched_name = name
            matched_steamid = _row_steamid(row)

    return matched_name is not None, matched_name, matched_steamid, all_names


def _row_matches_player(
    row: dict[str, Any],
    nickname: str,
    matched_name: str | None,
    matched_steamid: int | None,
) -> bool:
    sid = _row_steamid(row)
    if matched_steamid is not None and sid is not None and sid == matched_steamid:
        return True
    pname = _row_player_name(row, "user_name", "name", "player_name", "attacker_name")
    if not pname:
        return False
    nick = nickname.strip().lower()
    target = (matched_name or nickname).strip().lower()
    pl = pname.lower()
    return pl == target or nick in pl or pl in nick


def extract_kill_death_events(
    death_rows: list[dict[str, Any]],
    matched_name: str | None,
    nickname: str,
) -> dict[str, Any]:
    """player_death eventlerinden kill/death sayar."""
    if not death_rows:
        return {
            "kills": 0,
            "deaths": 0,
            "weapons": [],
            "round_count": None,
        }

    nick = nickname.strip().lower()
    target = (matched_name or nickname).strip().lower()
    kills = deaths = 0
    weapons: dict[str, int] = {}
    rounds: set[int] = set()

    for row in death_rows:
        attacker = _row_player_name(row, "attacker_name", "attackerName")
        victim = _row_player_name(row, "user_name", "player_name", "victim_name", "userid")
        weapon = _row_player_name(row, "weapon", "weapon_name", "weapon_friendlyname")

        att_l = attacker.lower() if attacker else ""
        vic_l = victim.lower() if victim else ""

        if att_l and (att_l == target or nick in att_l or att_l in nick):
            kills += 1
            if weapon:
                weapons[weapon] = weapons.get(weapon, 0) + 1

        if vic_l and (vic_l == target or nick in vic_l or vic_l in nick):
            deaths += 1

        rnd = row.get("total_rounds_played") or row.get("round")
        if rnd is not None:
            try:
                rounds.add(int(rnd))
            except (TypeError, ValueError):
                pass

    round_count = max(rounds) if rounds else None
    top_weapons = sorted(weapons.items(), key=lambda x: -x[1])[:8]

    return {
        "kills": kills,
        "deaths": deaths,
        "weapons": [f"{w} ({c})" for w, c in top_weapons],
        "round_count": round_count,
    }


def extract_shot_events_if_available(
    parser: Any,
    matched_name: str | None,
    nickname: str,
    *,
    matched_steamid: int | None = None,
) -> dict[str, Any]:
    """weapon_fire eventlerini çıkarır (demoparser2 user_* kolonları)."""
    result: dict[str, Any] = {
        "available": False,
        "shot_count": 0,
        "gun_shot_count": 0,
        "rows": [],
        "columns": [],
        "velocity_field": None,
        "reason": "",
    }
    if not demoparser_available():
        result["reason"] = "demoparser2 kurulu değil."
        return result

    try:
        events = parser.list_game_events()
        if "weapon_fire" not in events:
            result["reason"] = "Bu demoda weapon_fire eventi yok."
            return result

        df = parser.parse_event(
            "weapon_fire",
            player=["X", "Y", "Z", "velocity", "name", "steamid", "tick"],
            other=["weapon"],
        )
        rows = _df_records(df)
        result["columns"] = list(df.columns) if hasattr(df, "columns") else []
        if not rows:
            result["reason"] = "weapon_fire eventi boş döndü."
            return result

        velocity_field = None
        for candidate in ("user_velocity", "velocity"):
            if candidate in result["columns"]:
                velocity_field = candidate
                break
        result["velocity_field"] = velocity_field

        filtered = [
            row for row in rows
            if _row_matches_player(row, nickname, matched_name, matched_steamid)
        ]
        gun_rows = [
            row for row in filtered
            if _is_gun_weapon(_row_player_name(row, "weapon", "weapon_name"))
        ]

        result["available"] = len(filtered) > 0
        result["shot_count"] = len(filtered)
        result["gun_shot_count"] = len(gun_rows)
        result["rows"] = gun_rows if gun_rows else filtered
        if not result["available"]:
            result["reason"] = "Oyuncuya ait shot event bulunamadı."
    except Exception as exc:
        result["reason"] = f"Shot event çıkarılamadı: {exc}"

    return result


def extract_player_ticks_if_available(
    parser: Any,
    matched_name: str | None,
    *,
    matched_steamid: int | None = None,
) -> dict[str, Any]:
    """Oyuncuya ait tick/velocity verisini çıkarır."""
    result: dict[str, Any] = {
        "available": False,
        "tick_count": 0,
        "velocity_ticks": 0,
        "rows": [],
        "columns": [],
        "reason": "",
        "velocity_field": None,
    }
    try:
        kwargs: dict[str, Any] = {}
        if matched_steamid is not None:
            kwargs["players"] = [matched_steamid]
        elif matched_name:
            result["reason"] = "SteamID yok; parse_ticks için steamid gerekli."
            return result

        df = parser.parse_ticks(["X", "Y", "Z", "velocity", "name", "steamid"], **kwargs)
        rows = _df_records(df)
        result["columns"] = list(df.columns) if hasattr(df, "columns") else []
        result["tick_count"] = len(rows)
        result["rows"] = rows
        velocity_field = "velocity" if "velocity" in result["columns"] else None
        result["velocity_field"] = velocity_field
        result["velocity_ticks"] = sum(
            1 for row in rows
            if not _is_nan(_speed_from_row(row))
        )
        result["available"] = result["tick_count"] > 0
        if not result["available"]:
            result["reason"] = "Tick verisi boş döndü."
        elif result["velocity_ticks"] == 0:
            result["reason"] = "Tick verisi var ancak velocity alanı boş."
    except Exception as exc:
        result["reason"] = f"Tick verisi alınamadı: {exc}"
    return result


def extract_duel_tick_rows(parser: Any) -> dict[str, Any]:
    """All-player tick rows required for duel/spotted resolution (no player filter)."""
    result: dict[str, Any] = {
        "available": False,
        "rows": [],
        "columns": [],
        "reason": "",
    }
    fields = [
        "X", "Y", "Z", "pitch", "yaw", "velocity", "max_speed",
        "ducked", "ducking", "team_num", "entity_id",
        "approximate_spotted_by", "spotted", "total_rounds_played",
        "active_weapon_name", "shots_fired",
    ]
    try:
        df = parser.parse_ticks(fields)
        rows = _df_records(df)
        result["columns"] = list(df.columns) if hasattr(df, "columns") else []
        result["rows"] = rows
        result["available"] = len(rows) > 0
        if not result["available"]:
            result["reason"] = "Duel tick verisi boş."
    except Exception as exc:
        result["reason"] = f"Duel tick verisi alınamadı: {exc}"
    return result


def extract_player_hurt_rows(parser: Any, events: list[str] | None = None) -> list[dict[str, Any]]:
    try:
        event_list = events
        if event_list is None:
            event_list = parser.list_game_events()
        if "player_hurt" not in (event_list or []):
            return []
        df = parser.parse_event("player_hurt")
        return _df_records(df)
    except Exception:
        return []


def _compute_v2_for_demo(
    *,
    demo_id: str,
    matched_steamid: int | None,
    shot_rows: list[dict[str, Any]],
    duel_tick_rows: list[dict[str, Any]],
    hurt_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    from src.duel_shot_context import build_shot_contexts
    from src.proper_counter_strafe_v2 import _empty_v2, compute_v2_weapon_breakdown

    if matched_steamid is None:
        return _empty_v2(reason="matched steamid unavailable")
    contexts = build_shot_contexts(
        demo_id=demo_id,
        shooter_steamid=str(matched_steamid),
        shot_rows=shot_rows,
        tick_rows=duel_tick_rows,
        hurt_rows=hurt_rows,
    )
    v2 = compute_v2_weapon_breakdown(contexts)
    v2["context_count"] = len(contexts)
    v2["engagement_context_count"] = sum(
        1 for c in contexts if c.get("engagement_verified")
    )
    return v2


def combine_proper_counter_strafe_v2(demo_v2_list: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine per-demo V2 results; headline stays spotted-only (+ spotted_and_hurt)."""
    import statistics as _stats

    from src import suite_config as cfg
    from src.proper_counter_strafe_v2 import (
        DIAGNOSTIC_BUCKETS,
        _coverage_pct,
        _empty_v2,
        _pct,
        sample_confidence_for_size,
    )

    all_demos = [m for m in demo_v2_list if isinstance(m, dict) and m]
    usable = [
        m for m in all_demos
        if isinstance(m.get("eligible_shots"), int) and int(m.get("eligible_shots") or 0) > 0
    ]
    if not usable:
        reason = "no spotted-eligible V2 rifle shots across demos"
        for m in all_demos:
            if m.get("unavailable_reason") not in (None, "", "Unavailable"):
                reason = str(m.get("unavailable_reason"))
                break
        out = _empty_v2(reason=reason)
        out["demo_count_with_v2"] = 0
        return out

    def _sum_int(key: str) -> int:
        return sum(int(m.get(key) or 0) for m in usable)

    eligible = _sum_int("eligible_shots")
    proper = _sum_int("proper_shots")
    first_el = _sum_int("first_bullet_eligible_shots")
    first_pr = 0
    for m in usable:
        fe = int(m.get("first_bullet_eligible_shots") or 0)
        fpct = m.get("first_bullet_proper_pct")
        if fe > 0 and isinstance(fpct, (int, float)):
            first_pr += int(round(fe * float(fpct) / 100.0))

    base_cand = sum(int(m.get("base_rifle_non_crouch_candidates") or 0) for m in all_demos)
    fb_base = sum(int(m.get("first_bullet_base_candidates") or 0) for m in all_demos)

    source_counts: dict[str, dict[str, Any]] = {}
    for bucket in DIAGNOSTIC_BUCKETS:
        n = proper_n = improper_n = fb_el = fb_pr = 0
        for m in all_demos:
            sc = (m.get("source_counts") or {}).get(bucket) or {}
            bn = int(sc.get("n") or 0)
            n += bn
            proper_n += int(sc.get("proper_shots") or 0)
            improper_n += int(sc.get("improper_shots") or 0)
            fe = int(sc.get("first_bullet_eligible_shots") or 0)
            fb_el += fe
            fpct = sc.get("first_bullet_proper_pct")
            if fe > 0 and isinstance(fpct, (int, float)):
                fb_pr += int(round(fe * float(fpct) / 100.0))
        source_counts[bucket] = {
            "n": n,
            "proper_shots": proper_n,
            "improper_shots": improper_n,
            "proper_counter_strafe_pct": _pct(proper_n, n),
            "first_bullet_eligible_shots": fb_el,
            "first_bullet_proper_pct": _pct(fb_pr, fb_el),
            "median_speed_ratio": "Unavailable",
            "p75_speed_ratio": "Unavailable",
        }

    medians = [
        float(m["median_speed_ratio"])
        for m in usable
        if isinstance(m.get("median_speed_ratio"), (int, float))
    ]
    p75s = [
        float(m["p75_speed_ratio"])
        for m in usable
        if isinstance(m.get("p75_speed_ratio"), (int, float))
    ]

    def _weapon_combine(key: str) -> dict[str, Any]:
        el = pr = fe = fpr = 0
        for m in usable:
            w = (m.get("by_weapon") or {}).get(key) or {}
            el += int(w.get("eligible_shots") or 0)
            pr += int(w.get("proper_shots") or 0)
            wfe = int(w.get("first_bullet_eligible_shots") or 0)
            fe += wfe
            fpct = w.get("first_bullet_proper_pct")
            if wfe > 0 and isinstance(fpct, (int, float)):
                fpr += int(round(wfe * float(fpct) / 100.0))
        return {
            "eligible_shots": el,
            "proper_shots": pr,
            "proper_counter_strafe_pct": _pct(pr, el),
            "first_bullet_eligible_shots": fe,
            "first_bullet_proper_pct": _pct(fpr, fe),
            "sample_size": el,
            "sample_confidence": sample_confidence_for_size(el),
            "confidence": sample_confidence_for_size(el),
            "status": cfg.V2_STATUS_EXPERIMENTAL if el else cfg.V2_STATUS_UNAVAILABLE,
            "experimental": True,
            "measurement_quality": cfg.V2_MEASUREMENT_QUALITY_EXPERIMENTAL,
            "unavailable_reason": "Unavailable" if el else f"no spotted-eligible {key.upper()} V2 shots",
            "eligibility_source": cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED,
            "display_title": cfg.V2_DISPLAY_TITLE,
            "coach_soft_label": cfg.V2_COACH_SOFT_LABEL,
        }

    return {
        "metric_label": cfg.V2_METRIC_LABEL,
        "display_title": cfg.V2_DISPLAY_TITLE,
        "legacy_metric_label": cfg.V2_LEGACY_METRIC_LABEL,
        "status": cfg.V2_STATUS_EXPERIMENTAL,
        "eligible_shots": eligible,
        "proper_shots": proper,
        "improper_shots": eligible - proper,
        "proper_counter_strafe_pct": _pct(proper, eligible),
        "first_bullet_eligible_shots": first_el,
        "first_bullet_proper_pct": _pct(first_pr, first_el),
        "median_speed_ratio": (
            round(_stats.median(medians), 4) if medians else "Unavailable"
        ),
        "p75_speed_ratio": round(_stats.median(p75s), 4) if p75s else "Unavailable",
        "sample_size": eligible,
        "sample_confidence": sample_confidence_for_size(eligible),
        "confidence": sample_confidence_for_size(eligible),
        "measurement_quality": cfg.V2_MEASUREMENT_QUALITY_EXPERIMENTAL,
        "eligibility_source": cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED,
        "unavailable_reason": "Unavailable",
        "experimental": True,
        "coach_soft_label": cfg.V2_COACH_SOFT_LABEL,
        "base_rifle_non_crouch_candidates": base_cand,
        "spotted_eligible_shots": eligible,
        "eligibility_coverage_pct": _coverage_pct(eligible, base_cand),
        "first_bullet_base_candidates": fb_base,
        "first_bullet_spotted_eligible_shots": first_el,
        "first_bullet_eligibility_coverage_pct": _coverage_pct(first_el, fb_base),
        "source_counts": source_counts,
        "demo_count_with_v2": len(usable),
        "by_weapon": {
            "ak": _weapon_combine("ak"),
            "m4": _weapon_combine("m4"),
        },
    }


def _speed_from_row(row: dict[str, Any]) -> float | None:
    for key in ("user_velocity", "velocity_scalar", "velocity", "speed", "velocity_length"):
        val = row.get(key)
        if _is_nan(val):
            continue
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            try:
                return (float(val[0]) ** 2 + float(val[1]) ** 2) ** 0.5
            except (TypeError, ValueError):
                continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return None


def _tick_int(row: dict[str, Any]) -> int | None:
    try:
        tick = row.get("tick")
        return int(tick) if tick is not None else None
    except (TypeError, ValueError):
        return None


def _moving_status(speed: float | None) -> str:
    if speed is None:
        return "unknown"
    if speed <= STOPPED_SPEED_THRESHOLD:
        return "stopped"
    if speed <= MOVING_SPEED_THRESHOLD:
        return "micro_moving"
    return "moving"


def _is_ak_m4_weapon(weapon: str | None) -> bool:
    if not weapon:
        return False
    w = weapon.lower()
    return "ak47" in w or "m4a1" in w


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _group_shot_bursts(gun_rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Aynı silah + yakın tick aralığındaki ardışık atışları burst olarak gruplar."""
    sorted_rows = sorted(
        [row for row in gun_rows if _tick_int(row) is not None],
        key=lambda row: _tick_int(row) or 0,
    )
    bursts: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    prev_tick: int | None = None
    prev_weapon: str | None = None

    for row in sorted_rows:
        tick = _tick_int(row)
        weapon = _row_player_name(row, "weapon", "weapon_name")
        if (
            current
            and tick is not None
            and prev_tick is not None
            and weapon == prev_weapon
            and tick - prev_tick <= SPRAY_GAP_TICKS
        ):
            current.append(row)
        else:
            if current:
                bursts.append(current)
            current = [row]
        prev_tick = tick
        prev_weapon = weapon

    if current:
        bursts.append(current)
    return bursts


def _shot_debug_row(row: dict[str, Any]) -> dict[str, Any]:
    speed = _speed_from_row(row)
    return {
        "tick": _tick_int(row),
        "weapon": _row_player_name(row, "weapon", "weapon_name"),
        "user_name": _row_player_name(row, "user_name", "name"),
        "user_steamid": _row_steamid(row),
        "user_velocity": speed,
        "moving_status": _moving_status(speed),
    }


def _generate_mechanics_commentary(metrics: dict[str, Any], *, rifle_only: bool = False) -> list[str]:
    notes: list[str] = []
    prefix = "rifle_" if rifle_only else ""
    moving_pct = metrics.get(f"{prefix}shots_while_moving_pct", metrics.get("shots_while_moving_pct"))
    first_pct = metrics.get(f"{prefix}first_bullet_moving_pct", metrics.get("first_bullet_moving_pct"))
    long_spray = metrics.get(f"{prefix}long_spray_pct", metrics.get("long_spray_pct"))
    confidence = metrics.get(f"{prefix}metrics_confidence", metrics.get("metrics_confidence", "none"))

    if confidence == "none":
        return ["Velocity verisi yetersiz; kesin counter-strafe yorumu yapılmadı."]

    if isinstance(moving_pct, (int, float)) and moving_pct >= HIGH_MOVING_PCT:
        notes.append("Counter-strafe problemi şüphesi.")
    if isinstance(first_pct, (int, float)) and first_pct >= HIGH_FIRST_BULLET_MOVING_PCT:
        notes.append("İlk mermi stabilitesi sorunu.")
    if isinstance(long_spray, (int, float)) and long_spray >= HIGH_LONG_SPRAY_PCT:
        notes.append("Uzun spray alışkanlığı var; burst/reset çalış.")
    if not notes:
        scope = "Rifle" if rifle_only else "Genel"
        notes.append(f"{scope}: belirgin counter-strafe/spray sinyali yok; demo parser ilk sürüm sinyalidir.")
    return notes


def _generate_rifle_commentary(
    merged: dict[str, Any],
    ak_metrics: dict[str, Any],
    m4_metrics: dict[str, Any],
) -> list[str]:
    confidence = merged.get("rifle_metrics_confidence", "none")
    if confidence == "none":
        return ["Rifle velocity verisi yetersiz; counter-strafe teşhisi yapılmadı."]

    notes: list[str] = []
    ak_first = ak_metrics.get("first_bullet_moving_pct")
    m4_long = m4_metrics.get("long_spray_pct")
    rifle_mov = merged.get("rifle_shots_while_moving_pct")
    rifle_first = merged.get("rifle_first_bullet_moving_pct")
    rifle_long = merged.get("rifle_long_spray_pct")

    if isinstance(ak_first, (int, float)) and ak_first >= HIGH_FIRST_BULLET_MOVING_PCT:
        notes.append("AK: counter-strafe timing problemi — ilk mermi çok sık hareket halinde.")
    if isinstance(m4_long, (int, float)) and m4_long >= HIGH_LONG_SPRAY_PCT:
        notes.append("M4: spray reset problemi — uzun spray oranı yüksek.")
    if isinstance(rifle_mov, (int, float)) and rifle_mov >= HIGH_MOVING_PCT:
        notes.append("Rifle genel: hareket halinde ateş oranı yüksek; counter-strafe reset eksik.")
    elif isinstance(rifle_first, (int, float)) and rifle_first >= HIGH_FIRST_BULLET_MOVING_PCT:
        notes.append("Rifle genel: ilk mermi stabilitesi zayıf.")
    elif isinstance(rifle_long, (int, float)) and rifle_long >= HIGH_LONG_SPRAY_PCT:
        notes.append("Rifle genel: uzun spray alışkanlığı; burst/reset çalış.")
    if not notes:
        notes.append("Rifle: belirgin counter-strafe/spray sinyali yok.")
    return notes


def _generate_pistol_commentary(merged: dict[str, Any]) -> list[str]:
    confidence = merged.get("pistol_metrics_confidence", "none")
    total = merged.get("pistol_total_shots", 0) or 0
    if confidence == "none" or total < MIN_PISTOL_SHOTS_FOR_COMMENTARY:
        return ["Pistol velocity verisi yetersiz; kesin pistol yorumu yapılmadı."]

    notes: list[str] = []
    starter_first = merged.get("starter_pistol_first_bullet_moving_pct")
    starter_mov = merged.get("starter_pistol_shots_while_moving_pct")
    force_mov = merged.get("force_pistol_shots_while_moving_pct")
    deagle_first = merged.get("deagle_first_bullet_moving_pct")

    if isinstance(starter_first, (int, float)) and starter_first > 50:
        notes.append("Pistol round ilk mermi stabilitesi zayıf.")
    if isinstance(starter_mov, (int, float)) and starter_mov > 35:
        notes.append("USP/Glock düellolarında ADAD sırasında erken click var.")
    if isinstance(force_mov, (int, float)) and force_mov > 60:
        notes.append(
            "Force pistol hareketli spam yüksek; Tec-9/Five-Seven için kısmen normal "
            "ama rifle disipliniyle karıştırma."
        )
    if isinstance(deagle_first, (int, float)) and deagle_first > 30:
        notes.append("Deagle'da durmadan ateş etme problemi var.")
    if not notes:
        notes.append("Pistol: belirgin stabilite/spam sinyali yok.")
    return notes


def _generate_smg_commentary(merged: dict[str, Any]) -> list[str]:
    confidence = merged.get("smg_metrics_confidence", "none")
    if confidence == "none":
        return ["SMG velocity verisi yetersiz; SMG yorumu yapılmadı."]
    mov = merged.get("smg_shots_while_moving_pct")
    if isinstance(mov, (int, float)) and mov >= 55:
        return ["SMG: hareket halinde spam yüksek — SMG için beklenen; pistol/rifle ile karıştırma."]
    return ["SMG: pistol/rifle counter-strafe teşhisine dahil edilmez."]


def match_shots_to_tick_velocity(
    shot_rows: list[dict[str, Any]],
    tick_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Shot event tick değerleriyle player tick velocity eşleştirir."""
    tick_velocity: dict[int, float] = {}
    for row in tick_rows:
        tick = _tick_int(row)
        speed = _speed_from_row(row)
        if tick is None or speed is None:
            continue
        tick_velocity[tick] = speed

    matched: list[dict[str, Any]] = []
    for shot in shot_rows:
        tick = _tick_int(shot)
        speed = _speed_from_row(shot)
        source = "shot_event" if speed is not None else None

        if speed is None and tick is not None:
            if tick in tick_velocity:
                speed = tick_velocity[tick]
                source = "tick_exact"
            else:
                for delta in (0, 1, 2, -1, -2):
                    candidate = tick + delta
                    if candidate in tick_velocity:
                        speed = tick_velocity[candidate]
                        source = "tick_nearest"
                        break

        matched.append({
            **shot,
            "matched_speed": speed,
            "speed_source": source,
        })
    return matched


def _mechanics_confidence(matched_with_speed: int, total_shots: int) -> str:
    if total_shots <= 0 or matched_with_speed <= 0:
        return "none"
    ratio = matched_with_speed / total_shots
    if ratio >= 0.8:
        return "medium"
    if ratio >= 0.4:
        return "low"
    return "none"


def _prefix_mechanics(
    metrics: dict[str, Any],
    prefix: str,
    *,
    spam_terms: bool = False,
) -> dict[str, Any]:
    """Metrik anahtarlarına prefix ekler (örn. rifle_total_shots)."""
    skip = {
        "weapon_shot_counts", "ak_m4_shot_counts", "speed_sources", "commentary", "_raw",
        "ak_metrics", "m4_metrics", "pistol_metrics", "smg_metrics",
        "starter_pistol_metrics", "force_pistol_metrics", "deagle_metrics", "revolver_metrics",
        "rifle_commentary", "pistol_commentary", "smg_commentary", "counter_strafe_commentary",
    }
    out: dict[str, Any] = {}
    for key, val in metrics.items():
        if key in skip or key.startswith(f"{prefix}_"):
            continue
        out_key = f"{prefix}_{key}"
        if spam_terms:
            if key == "spray_length_average":
                out_key = f"{prefix}_spam_length_average"
            elif key == "long_spray_pct":
                out_key = f"{prefix}_long_spam_pct"
        out[out_key] = val
    return out


def _compute_shot_mechanics(
    shot_rows: list[dict[str, Any]],
    *,
    tick_rows: list[dict[str, Any]] | None = None,
    weapon_filter: Any | None = None,
) -> dict[str, Any]:
    """user_velocity (shot event) tabanlı counter-strafe / spray ön metrikleri."""
    rows = match_shots_to_tick_velocity(shot_rows, tick_rows or [])
    if weapon_filter is not None:
        gun_rows = [
            row for row in rows
            if weapon_filter(_row_player_name(row, "weapon", "weapon_name"))
        ]
    else:
        gun_rows = [
            row for row in rows
            if _is_gun_weapon(_row_player_name(row, "weapon", "weapon_name"))
        ] or rows

    total_shots = len(gun_rows)
    speeds: list[float] = []
    moving_shots = 0
    weapon_counts: dict[str, int] = {}
    matched_with_velocity = 0
    source_counts: dict[str, int] = {}

    for row in gun_rows:
        speed = row.get("matched_speed")
        if speed is None:
            speed = _speed_from_row(row)
        source = row.get("speed_source") or ("shot_event" if speed is not None else "none")
        weapon = _row_player_name(row, "weapon", "weapon_name") or "unknown"
        weapon_counts[weapon] = weapon_counts.get(weapon, 0) + 1

        if speed is not None:
            matched_with_velocity += 1
            speed_f = float(speed)
            source_counts[source or "unknown"] = source_counts.get(source or "unknown", 0) + 1
            speeds.append(speed_f)
            if _moving_status(speed_f) == "moving":
                moving_shots += 1

    bursts = _group_shot_bursts(gun_rows)
    burst_lengths = [len(burst) for burst in bursts]
    long_spray_bursts = sum(1 for length in burst_lengths if length >= LONG_SPRAY_MIN_SHOTS)

    first_bullet_moving = 0
    bursts_with_first_velocity = 0
    ak_m4_burst_lengths: list[int] = []

    for burst in bursts:
        if not burst:
            continue
        first = burst[0]
        first_speed = first.get("matched_speed")
        if first_speed is None:
            first_speed = _speed_from_row(first)
        weapon = _row_player_name(first, "weapon", "weapon_name")
        if _is_ak_m4_weapon(weapon):
            ak_m4_burst_lengths.append(len(burst))
        if first_speed is None:
            continue
        bursts_with_first_velocity += 1
        if _moving_status(float(first_speed)) == "moving":
            first_bullet_moving += 1

    metrics_confidence = _mechanics_confidence(matched_with_velocity, total_shots)
    reliable = matched_with_velocity >= MIN_SHOTS_FOR_METRICS and metrics_confidence != "none"

    metrics: dict[str, Any] = {
        "reliable": reliable,
        "metrics_confidence": metrics_confidence,
        "total_shots": total_shots,
        "shots_with_velocity": matched_with_velocity,
        "velocity_match_pct": (
            round(matched_with_velocity / total_shots * 100, 1) if total_shots else 0
        ),
        "velocity_fields_found": matched_with_velocity > 0,
        "velocity_source": "user_velocity",
        "speed_sources": source_counts,
        "burst_count": len(bursts),
        "moving_shots": moving_shots,
        "first_bullet_moving": first_bullet_moving,
        "bursts_with_first_velocity": bursts_with_first_velocity,
        "long_spray_bursts": long_spray_bursts,
        "burst_length_sum": sum(burst_lengths),
        "speed_sum": sum(speeds),
        "shots_while_moving_pct": MISSING_DATA_LABEL,
        "first_bullet_moving_pct": MISSING_DATA_LABEL,
        "average_speed_at_shot": MISSING_DATA_LABEL,
        "median_speed_at_shot": MISSING_DATA_LABEL,
        "spray_length_average": MISSING_DATA_LABEL,
        "long_spray_pct": MISSING_DATA_LABEL,
        "ak_m4_burst_average": MISSING_DATA_LABEL,
        "weapon_shot_counts": weapon_counts,
        "ak_m4_shot_counts": {
            w: c for w, c in weapon_counts.items() if _is_ak_m4_weapon(w)
        },
        "commentary": [],
        "note": "",
    }

    if not reliable:
        if matched_with_velocity == 0:
            metrics["note"] = (
                "Shot event var ama user_velocity alanı bulunamadı veya eşleşmedi."
            )
        else:
            metrics["note"] = (
                f"Yalnızca {matched_with_velocity}/{total_shots} shot user_velocity ile eşleşti; "
                "güven düşük — veri yetersiz."
            )
        return metrics

    median_speed = _median(speeds)
    metrics.update({
        "shots_while_moving_pct": round(moving_shots / matched_with_velocity * 100, 1),
        "first_bullet_moving_pct": round(
            first_bullet_moving / bursts_with_first_velocity * 100, 1,
        ) if bursts_with_first_velocity else 0,
        "average_speed_at_shot": round(sum(speeds) / len(speeds), 1),
        "median_speed_at_shot": round(median_speed, 1) if median_speed is not None else MISSING_DATA_LABEL,
        "spray_length_average": round(sum(burst_lengths) / len(burst_lengths), 1) if burst_lengths else MISSING_DATA_LABEL,
        "long_spray_pct": round(long_spray_bursts / len(bursts) * 100, 1) if bursts else 0,
        "ak_m4_burst_average": (
            round(sum(ak_m4_burst_lengths) / len(ak_m4_burst_lengths), 1)
            if ak_m4_burst_lengths else MISSING_DATA_LABEL
        ),
    })
    metrics["commentary"] = _generate_mechanics_commentary(metrics)
    metrics["note"] = (
        f"{matched_with_velocity}/{total_shots} shot user_velocity ile eşleşti "
        f"({metrics['velocity_match_pct']}%). "
        + " ".join(metrics["commentary"])
        + " Kesin spray kontrolü teşhisi değil; mermi dağılımı/hit doğrulaması sınırlı."
    )
    return metrics


def _build_full_mechanics(
    shot_rows: list[dict[str, Any]],
    *,
    tick_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Tüm silah + rifle + pistol + SMG metrik paketi."""
    base = _compute_shot_mechanics(shot_rows, tick_rows=tick_rows)
    rifle = _compute_shot_mechanics(shot_rows, tick_rows=tick_rows, weapon_filter=_is_rifle_weapon)
    ak = _compute_shot_mechanics(shot_rows, tick_rows=tick_rows, weapon_filter=_is_ak_weapon)
    m4 = _compute_shot_mechanics(shot_rows, tick_rows=tick_rows, weapon_filter=_is_m4_weapon)
    pistol = _compute_shot_mechanics(shot_rows, tick_rows=tick_rows, weapon_filter=_is_pistol_weapon)
    smg = _compute_shot_mechanics(shot_rows, tick_rows=tick_rows, weapon_filter=_is_smg_weapon)
    starter = _compute_shot_mechanics(shot_rows, tick_rows=tick_rows, weapon_filter=_is_starter_pistol_weapon)
    force = _compute_shot_mechanics(shot_rows, tick_rows=tick_rows, weapon_filter=_is_force_pistol_weapon)
    deagle = _compute_shot_mechanics(shot_rows, tick_rows=tick_rows, weapon_filter=_is_deagle_weapon)
    revolver = _compute_shot_mechanics(shot_rows, tick_rows=tick_rows, weapon_filter=_is_revolver_weapon)

    merged = {**base}
    merged.update(_prefix_mechanics(rifle, "rifle"))
    merged.update(_prefix_mechanics(pistol, "pistol", spam_terms=True))
    merged.update(_prefix_mechanics(smg, "smg"))
    merged.update(_prefix_mechanics(starter, "starter_pistol", spam_terms=True))
    merged.update(_prefix_mechanics(force, "force_pistol", spam_terms=True))
    merged.update(_prefix_mechanics(deagle, "deagle", spam_terms=True))
    merged.update(_prefix_mechanics(revolver, "revolver", spam_terms=True))
    merged["ak_metrics"] = ak
    merged["m4_metrics"] = m4
    merged["pistol_metrics"] = pistol
    merged["smg_metrics"] = smg
    merged["starter_pistol_metrics"] = starter
    merged["force_pistol_metrics"] = force
    merged["deagle_metrics"] = deagle
    merged["revolver_metrics"] = revolver
    merged["rifle_commentary"] = _generate_rifle_commentary(merged, ak, m4)
    merged["pistol_commentary"] = _generate_pistol_commentary(merged)
    merged["smg_commentary"] = _generate_smg_commentary(merged)
    merged["counter_strafe_commentary"] = merged["rifle_commentary"]
    merged["commentary"] = merged["rifle_commentary"]
    return merged


def combine_mechanics_metrics(metrics_list: list[dict[str, Any]], *, prefix: str = "") -> dict[str, Any]:
    """Birden fazla demo metrik paketini ağırlıklı birleştirir."""
    key = lambda name: f"{prefix}{name}" if prefix else name
    valid = [m for m in metrics_list if m.get(key("total_shots"), m.get("total_shots", 0)) > 0]
    if not valid:
        return {"reliable": False, "metrics_confidence": "none", "note": "Birleştirilecek veri yok."}

    def _sum_field(name: str) -> int | float:
        return sum(
            m.get(key(name), m.get(name, 0)) or 0
            for m in valid
        )

    total_shots = int(_sum_field("total_shots"))
    matched = int(_sum_field("shots_with_velocity"))
    moving = int(_sum_field("moving_shots"))
    first_mov = int(_sum_field("first_bullet_moving"))
    bursts_first = int(_sum_field("bursts_with_first_velocity"))
    long_spray = int(_sum_field("long_spray_bursts"))
    burst_count = int(_sum_field("burst_count"))
    burst_len_sum = int(_sum_field("burst_length_sum"))
    speed_sum = float(_sum_field("speed_sum"))

    confidence = _mechanics_confidence(matched, total_shots)
    reliable = matched >= MIN_SHOTS_FOR_METRICS and confidence != "none"

    out_key = lambda n: f"{prefix}{n}" if prefix else n

    combined: dict[str, Any] = {
        out_key("reliable"): reliable,
        out_key("metrics_confidence"): confidence,
        out_key("total_shots"): total_shots,
        out_key("shots_with_velocity"): matched,
        out_key("burst_count"): burst_count,
        out_key("moving_shots"): moving,
        out_key("first_bullet_moving"): first_mov,
        out_key("bursts_with_first_velocity"): bursts_first,
        out_key("long_spray_bursts"): long_spray,
        out_key("burst_length_sum"): burst_len_sum,
        out_key("speed_sum"): speed_sum,
        out_key("note"): "",
    }

    if not reliable:
        combined[out_key("note")] = (
            f"Combined {prefix or 'genel'}: velocity verisi yetersiz ({matched}/{total_shots})."
        )
        return combined

    combined.update({
        out_key("shots_while_moving_pct"): round(moving / matched * 100, 1) if matched else 0,
        out_key("first_bullet_moving_pct"): round(
            first_mov / bursts_first * 100, 1,
        ) if bursts_first else 0,
        out_key("average_speed_at_shot"): round(speed_sum / matched, 1) if matched else MISSING_DATA_LABEL,
        out_key("spray_length_average"): round(
            burst_len_sum / burst_count, 1,
        ) if burst_count else MISSING_DATA_LABEL,
        out_key("long_spray_pct"): round(long_spray / burst_count * 100, 1) if burst_count else 0,
        out_key("velocity_match_pct"): round(matched / total_shots * 100, 1) if total_shots else 0,
    })
    combined[out_key("commentary")] = _generate_mechanics_commentary(
        combined, rifle_only=bool(prefix),
    )
    if prefix:
        combined[out_key("counter_strafe_commentary")] = combined[out_key("commentary")]
    return combined


def collect_demo_debug_info(
    demo_path: str | Path,
    nickname: str,
) -> dict[str, Any]:
    """Demo parser debug bilgisi toplar."""
    path = Path(demo_path)
    info: dict[str, Any] = {
        "demo_file": path.name,
        "demo_path": str(path.resolve()),
        "parser_version": get_demoparser_version(),
        "methods_used": [],
        "nickname": nickname,
        "errors": [],
    }
    if not demoparser_available():
        info["errors"].append("demoparser2 kurulu değil.")
        return info

    try:
        from demoparser2 import DemoParser

        parser = DemoParser(str(path))
        info["methods_used"] = [
            "DemoParser",
            "parse_player_info",
            "list_game_events",
            "parse_event(player_death)",
            "parse_event(weapon_fire)",
            "parse_ticks",
        ]

        player_info = parser.parse_player_info()
        matched, matched_name, matched_steamid, all_names = _resolve_player_names(
            player_info, nickname,
        )
        info["player_matched"] = matched
        info["matched_name"] = matched_name
        info["matched_steamid"] = matched_steamid
        info["players_in_demo"] = all_names
        info["player_info_columns"] = (
            list(player_info.columns) if hasattr(player_info, "columns") else []
        )

        events = parser.list_game_events()
        info["game_events_sample"] = [
            e for e in events
            if any(k in e.lower() for k in ("fire", "shot", "weapon", "death"))
        ][:20]

        death_cols: list[str] = []
        death_sample: list[dict[str, Any]] = []
        if "player_death" in events:
            death_df = parser.parse_event(
                "player_death",
                player=["X", "Y", "name", "steamid"],
                other=["weapon", "total_rounds_played", "attacker_name", "attacker_steamid"],
            )
            death_cols = list(death_df.columns) if hasattr(death_df, "columns") else []
            death_sample = _df_records(death_df)[:5]

        shots = extract_shot_events_if_available(
            parser, matched_name, nickname, matched_steamid=matched_steamid,
        )
        ticks = extract_player_ticks_if_available(
            parser, matched_name, matched_steamid=matched_steamid,
        )
        shot_sample = [_shot_debug_row(row) for row in (shots.get("rows") or [])[:10]]
        tick_sample = (ticks.get("rows") or [])[:5]
        matched_shots = match_shots_to_tick_velocity(
            shots.get("rows") or [], ticks.get("rows") or [],
        )
        mechanics_preview = _build_full_mechanics(
            shots.get("rows") or [], tick_rows=ticks.get("rows") or [],
        )

        common_keys = []
        if shots.get("columns") and ticks.get("columns"):
            common_keys = sorted(set(shots["columns"]) & set(ticks["columns"]))

        info.update({
            "death_columns": death_cols,
            "death_sample": death_sample,
            "shot_columns": shots.get("columns") or [],
            "shot_sample": shot_sample,
            "tick_columns": ticks.get("columns") or [],
            "tick_sample": tick_sample,
            "shot_velocity_field": shots.get("velocity_field"),
            "tick_velocity_field": ticks.get("velocity_field"),
            "shot_count": shots.get("shot_count", 0),
            "tick_count": ticks.get("tick_count", 0),
            "velocity_ticks": ticks.get("velocity_ticks", 0),
            "common_keys": common_keys,
            "tick_on_shots": all(_tick_int(s) is not None for s in (shots.get("rows") or [])[:10]),
            "steamid_on_shots": all(_row_steamid(s) is not None for s in (shots.get("rows") or [])[:10]),
            "matched_shot_sample": matched_shots[:5],
            "matched_with_velocity": sum(
                1 for row in matched_shots if row.get("matched_speed") is not None
            ),
            "mechanics_preview": mechanics_preview,
        })
    except Exception as exc:
        info["errors"].append(str(exc))

    return info


def render_demo_debug_markdown(debug: dict[str, Any]) -> str:
    lines = [
        f"# Demo Parser Debug — {debug.get('demo_file', '?')}",
        "",
        f"*Parser version:* {debug.get('parser_version')}",
        "",
        "## Kullanılan metodlar",
        "",
    ]
    for method in debug.get("methods_used") or []:
        lines.append(f"- {method}")
    lines.append("")

    if debug.get("errors"):
        lines.extend(["## Hatalar", ""])
        for err in debug["errors"]:
            lines.append(f"- {err}")
        lines.append("")

    lines.extend([
        "## Oyuncu eşleşmesi",
        "",
        f"- Nickname: {debug.get('nickname')}",
        f"- Eşleşme: {debug.get('player_matched')}",
        f"- İsim: {debug.get('matched_name')}",
        f"- SteamID: {debug.get('matched_steamid')}",
        "",
        "## Kolon isimleri",
        "",
        f"- player_info: `{', '.join(debug.get('player_info_columns') or [])}`",
        f"- player_death: `{', '.join(debug.get('death_columns') or [])}`",
        f"- weapon_fire: `{', '.join(debug.get('shot_columns') or [])}`",
        f"- parse_ticks: `{', '.join(debug.get('tick_columns') or [])}`",
        "",
        f"- Shot velocity alanı: {debug.get('shot_velocity_field')}",
        f"- Tick velocity alanı: {debug.get('tick_velocity_field')}",
        "",
        "## Event örnekleri",
        "",
        f"- Shot event sayısı: {debug.get('shot_count')}",
        f"- Player tick sayısı: {debug.get('tick_count')}",
        f"- Velocity'li tick sayısı: {debug.get('velocity_ticks')}",
        f"- Eşleşen shot+velocity: {debug.get('matched_with_velocity')}",
        "",
        "### İlk 10 shot event (Jurses)",
        "",
        "| tick | weapon | user_name | user_steamid | user_velocity | moving_status |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for row in debug.get("shot_sample") or []:
        lines.append(
            f"| {row.get('tick')} | {row.get('weapon')} | {row.get('user_name')} | "
            f"{row.get('user_steamid')} | {row.get('user_velocity')} | {row.get('moving_status')} |"
        )
    preview = debug.get("mechanics_preview") or {}
    if preview:
        lines.extend([
            "",
            "## user_velocity metrik önizleme",
            "",
            f"- total_shots: {preview.get('total_shots')}",
            f"- shots_with_velocity: {preview.get('shots_with_velocity')}",
            f"- average_speed_at_shot: {preview.get('average_speed_at_shot')}",
            f"- median_speed_at_shot: {preview.get('median_speed_at_shot')}",
            f"- shots_while_moving_pct: {preview.get('shots_while_moving_pct')}",
            f"- first_bullet_moving_pct: {preview.get('first_bullet_moving_pct')}",
            f"- spray_length_average: {preview.get('spray_length_average')}",
            f"- long_spray_pct: {preview.get('long_spray_pct')}",
            f"- confidence: {preview.get('metrics_confidence')}",
            "",
        ])
    lines.extend([
        "",
        "### İlk 5 player tick",
        "",
    ])
    for row in debug.get("tick_sample") or []:
        lines.append(
            f"- tick={row.get('tick')} velocity={row.get('velocity')} "
            f"name={row.get('name')} steamid={row.get('steamid')}"
        )
    lines.extend([
        "",
        "## Eşleşme analizi",
        "",
        f"- Ortak kolonlar: `{', '.join(debug.get('common_keys') or []) or 'yok'}`",
        f"- Shot eventlerinde tick var mı: {debug.get('tick_on_shots')}",
        f"- Shot eventlerinde steamid var mı: {debug.get('steamid_on_shots')}",
        "",
        "### İlk 5 eşleşmiş shot",
        "",
    ])
    for row in debug.get("matched_shot_sample") or []:
        lines.append(
            f"- tick={row.get('tick')} speed={row.get('matched_speed')} "
            f"source={row.get('speed_source')} weapon={row.get('weapon')}"
        )
    lines.append("")
    return "\n".join(lines)


def write_demo_debug_report(path: Path, debug: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_demo_debug_markdown(debug), encoding="utf-8")
    return path


def parse_demo_basic(
    demo_path: str | Path,
    nickname: str,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    """Tek bir .dem dosyasını güvenli şekilde parse eder."""
    path = Path(demo_path)
    base = {
        "demo_file": path.name,
        "demo_path": str(path.resolve()),
        "parser": "demoparser2" if demoparser_available() else "none",
    }

    if not path.exists():
        return {**base, **_unavailable("Demo dosyası bulunamadı.")}

    name_lower = path.name.lower()
    if any(name_lower.endswith(ext) for ext in COMPRESSED_EXTENSIONS):
        return {
            **base,
            **_unavailable(
                "Sıkıştırılmış demo doğrudan parse edilemez; prepare_demos_for_parsing kullanın."
            ),
        }

    if not demoparser_available():
        return {**base, **_unavailable("demoparser2 kurulu değil. pip install demoparser2")}

    try:
        from demoparser2 import DemoParser

        parser = DemoParser(str(path))
        player_info = parser.parse_player_info()
        matched, matched_name, matched_steamid, all_names = _resolve_player_names(
            player_info, nickname,
        )

        death_df = None
        events = []
        try:
            events = parser.list_game_events()
        except Exception:
            events = []

        if "player_death" in events:
            death_df = parser.parse_event(
                "player_death",
                player=["X", "Y", "name", "steamid"],
                other=["weapon", "total_rounds_played", "attacker_name"],
            )

        death_rows = _df_records(death_df)
        kd = extract_kill_death_events(death_rows, matched_name, nickname)
        shots = extract_shot_events_if_available(
            parser, matched_name, nickname, matched_steamid=matched_steamid,
        )
        ticks = extract_player_ticks_if_available(
            parser, matched_name, matched_steamid=matched_steamid,
        )

        mechanics: dict[str, Any] = {
            "reliable": False,
            "metrics_confidence": "none",
            "note": "Shot event var ama player velocity alanı bulunamadı.",
        }
        if shots.get("available") and shots.get("rows"):
            mechanics = _build_full_mechanics(
                shots["rows"],
                tick_rows=ticks.get("rows") or [],
            )

        duel_ticks = extract_duel_tick_rows(parser)
        hurt_rows = extract_player_hurt_rows(parser, events)
        proper_cs_v2 = _compute_v2_for_demo(
            demo_id=path.name,
            matched_steamid=matched_steamid,
            shot_rows=shots.get("rows") or [],
            duel_tick_rows=duel_ticks.get("rows") or [],
            hurt_rows=hurt_rows,
        )
        mechanics["proper_counter_strafe_v2"] = proper_cs_v2
        mechanics["legacy_metric_label"] = "legacy_first_bullet_moving"

        confidence = mechanics.get("rifle_metrics_confidence", mechanics.get("metrics_confidence", "none"))
        if matched and kd["kills"] + kd["deaths"] > 0 and confidence == "none":
            confidence = "low"

        if matched:
            from src.impact_analyzer import analyze_impact_from_parser

            impact = analyze_impact_from_parser(
                parser, nickname, matched_name, matched_steamid,
            )
        else:
            from src.impact_analyzer import _empty_impact

            impact = _empty_impact(reason="Oyuncu demo içinde eşleşmedi.")

        result = {
            **base,
            "status": "ok",
            "reason": "",
            "demo_count": 1,
            "confidence": confidence,
            "parser_status": "ok",
            "player_matched": matched,
            "matched_name": matched_name,
            "matched_steamid": matched_steamid,
            "players_in_demo": all_names[:20],
            "kills": kd["kills"],
            "deaths": kd["deaths"],
            "weapons": kd["weapons"],
            "round_count": kd["round_count"],
            "shot_count": shots.get("shot_count", 0),
            "gun_shot_count": shots.get("gun_shot_count", 0),
            "tick_count": ticks.get("tick_count", 0),
            "velocity_ticks": ticks.get("velocity_ticks", 0),
            "tick_data_available": ticks.get("available", False),
            "tick_data_note": ticks.get("reason") or (
                f"{ticks.get('tick_count', 0)} tick, {ticks.get('velocity_ticks', 0)} velocity'li."
                if ticks.get("available") else "veri yetersiz"
            ),
            "shot_event_available": shots.get("available", False),
            "shot_event_note": shots.get("reason") or (
                f"{shots.get('shot_count', 0)} shot event okundu."
                if shots.get("available") else "veri yetersiz"
            ),
            "velocity_fields_found": mechanics.get("velocity_fields_found", False),
            "shots_with_velocity": mechanics.get("shots_with_velocity", 0),
            "mechanics": mechanics,
            "impact": impact,
            "proper_counter_strafe_v2": proper_cs_v2,
            "events_found": events[:15],
        }
        if debug:
            result["debug"] = collect_demo_debug_info(path, nickname)
        return result
    except Exception as exc:
        return {
            **base,
            **_unavailable(f"Demo okunamadı: {exc}"),
            "parser_status": "error",
        }


def build_mechanics_summary(
    demo_files: list[dict[str, Any]],
    parsed_demos: list[dict[str, Any]],
    *,
    demo_folder: Path,
    nickname: str,
    extractions: list[dict[str, Any]] | None = None,
    preparation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Birden fazla demo parse sonucunu özetler."""
    extractions = extractions or []
    preparation = preparation or {}
    parseable = [f for f in demo_files if f.get("parseable")]
    if preparation.get("parseable"):
        parseable = preparation["parseable"]
    compressed = [f for f in demo_files if f.get("compressed")]
    ok_demos = [p for p in parsed_demos if p.get("status") == "ok"]
    unavailable_demos = [p for p in parsed_demos if p.get("status") == "unavailable"]
    parser_attempted = len(parsed_demos) > 0
    mechanics_produced = any(
        d.get("mechanics", {}).get("rifle_reliable") or d.get("mechanics", {}).get("reliable")
        for d in ok_demos
    )

    if not demo_files:
        return {
            "status": "unavailable",
            "reason": "Demo klasöründe dosya yok.",
            "demo_count": 0,
            "confidence": "none",
            "folder": str(demo_folder.resolve()),
            "nickname": nickname,
            "parser": "demoparser2" if demoparser_available() else "none",
            "found_count": 0,
            "parsed_count": 0,
            "compressed_count": 0,
            "compressed_found": False,
            "compressed_note": "",
            "extractions": [],
            "parser_attempted": False,
            "parser_result": "denenmedi",
            "mechanics_produced": False,
            "demos": [],
            "aggregated": {},
        }

    extracted_ok = [e for e in extractions if e.get("extracted") and not e.get("error")]
    extraction_failed = [e for e in extractions if e.get("error")]

    compressed_note = ""
    if compressed:
        if extracted_ok:
            names = ", ".join(e.get("output", "?") for e in extracted_ok)
            compressed_note = f"Sıkıştırılmış demo bulundu ve .dem olarak hazırlandı: {names}"
        elif extraction_failed:
            compressed_note = (
                f"Sıkıştırılmış demo bulundu ancak çıkarılamadı: "
                f"{extraction_failed[0].get('error', 'bilinmeyen hata')}"
            )
        elif not parseable:
            compressed_note = "Sıkıştırılmış demo bulundu; çıkarma başarısız veya .dem oluşmadı."

    aggregated: dict[str, Any] = {
        "kills": sum(d.get("kills", 0) for d in ok_demos),
        "deaths": sum(d.get("deaths", 0) for d in ok_demos),
        "weapons": [],
        "round_count": None,
        "shot_count": sum(d.get("shot_count", 0) for d in ok_demos),
        "tick_count": sum(d.get("tick_count", 0) for d in ok_demos),
        "shots_with_velocity": sum(d.get("shots_with_velocity", 0) for d in ok_demos),
        "velocity_fields_found": any(d.get("velocity_fields_found") for d in ok_demos),
        "tick_data_available": any(d.get("tick_data_available") for d in ok_demos),
        "shot_event_available": any(d.get("shot_event_available") for d in ok_demos),
        "mechanics": {
            "reliable": False,
            "metrics_confidence": "none",
            "note": "Shot event var ama player velocity alanı bulunamadı.",
        },
    }

    reliable_mech = [
        d.get("mechanics", {}) for d in ok_demos
        if d.get("mechanics", {}).get("rifle_reliable") or d.get("mechanics", {}).get("reliable")
    ]
    per_demo_cards = []
    for d in parsed_demos:
        mech = d.get("mechanics") or {}
        imp = d.get("impact") or {}
        per_demo_cards.append({
            "demo_file": d.get("demo_file"),
            "player_matched": d.get("player_matched"),
            "kills": d.get("kills", 0),
            "deaths": d.get("deaths", 0),
            "round_count": d.get("round_count"),
            "total_shots": mech.get("total_shots", 0),
            "rifle_total_shots": mech.get("rifle_total_shots", 0),
            "rifle_first_bullet_moving_pct": mech.get("rifle_first_bullet_moving_pct"),
            "rifle_shots_while_moving_pct": mech.get("rifle_shots_while_moving_pct"),
            "rifle_long_spray_pct": mech.get("rifle_long_spray_pct"),
            "pistol_total_shots": mech.get("pistol_total_shots", 0),
            "pistol_first_bullet_moving_pct": mech.get("pistol_first_bullet_moving_pct"),
            "pistol_shots_while_moving_pct": mech.get("pistol_shots_while_moving_pct"),
            "pistol_long_spam_pct": mech.get("pistol_long_spam_pct"),
            "smg_total_shots": mech.get("smg_total_shots", 0),
            "smg_shots_while_moving_pct": mech.get("smg_shots_while_moving_pct"),
            "confidence": mech.get("rifle_metrics_confidence", mech.get("metrics_confidence", "none")),
            "pistol_confidence": mech.get("pistol_metrics_confidence", "none"),
            "status": d.get("status"),
            "opening_kills": imp.get("opening_kills"),
            "opening_deaths": imp.get("opening_deaths"),
            "opening_success_pct": imp.get("opening_duel_success_pct"),
            "trade_kills": imp.get("trade_kills"),
            "traded_deaths": imp.get("traded_deaths"),
            "untraded_deaths": imp.get("untraded_deaths"),
            "untraded_death_pct": imp.get("untraded_death_pct"),
            "early_death_pct": imp.get("early_death_pct"),
            "death_after_kill_5s_pct": imp.get("death_after_kill_within_5s_pct"),
            "post_kill_survival_rate_5s": imp.get("post_kill_survival_rate_5s"),
            "impact_rating_0_100": imp.get("impact_rating_0_100"),
            "impact_confidence": imp.get("metrics_confidence", "none"),
        })

    demo_impacts = [d.get("impact") or {} for d in ok_demos]
    from src.impact_analyzer import combine_impact_metrics

    aggregated["impact"] = combine_impact_metrics(demo_impacts)
    if aggregated["impact"].get("debug") is None:
        for d in ok_demos:
            dbg = (d.get("impact") or {}).get("debug")
            if dbg:
                aggregated["impact"]["debug"] = dbg
                break

    combined_rifle = combine_mechanics_metrics(reliable_mech, prefix="rifle_")
    combined_general = combine_mechanics_metrics(reliable_mech, prefix="")
    combined_pistol = combine_mechanics_metrics(reliable_mech, prefix="pistol_")
    combined_smg = combine_mechanics_metrics(reliable_mech, prefix="smg_")
    combined_ak = combine_mechanics_metrics(
        [m.get("ak_metrics", {}) for m in reliable_mech], prefix="",
    )
    combined_m4 = combine_mechanics_metrics(
        [m.get("m4_metrics", {}) for m in reliable_mech], prefix="",
    )
    combined_starter = combine_mechanics_metrics(
        [m.get("starter_pistol_metrics", {}) for m in reliable_mech], prefix="",
    )
    combined_force = combine_mechanics_metrics(
        [m.get("force_pistol_metrics", {}) for m in reliable_mech], prefix="",
    )
    combined_deagle = combine_mechanics_metrics(
        [m.get("deagle_metrics", {}) for m in reliable_mech], prefix="",
    )
    combined_revolver = combine_mechanics_metrics(
        [m.get("revolver_metrics", {}) for m in reliable_mech], prefix="",
    )

    if reliable_mech:
        def _avg(key: str) -> float | str:
            vals = [m[key] for m in reliable_mech if isinstance(m.get(key), (int, float))]
            return round(sum(vals) / len(vals), 1) if vals else MISSING_DATA_LABEL

        weapon_totals: dict[str, int] = {}
        ak_totals: dict[str, int] = {}
        for m in reliable_mech:
            for w, c in (m.get("weapon_shot_counts") or {}).items():
                weapon_totals[w] = weapon_totals.get(w, 0) + int(c)
            for w, c in (m.get("ak_m4_shot_counts") or {}).items():
                ak_totals[w] = ak_totals.get(w, 0) + int(c)

        pistol_commentary = _generate_pistol_commentary({
            "pistol_metrics_confidence": combined_pistol.get("pistol_metrics_confidence", "none"),
            "pistol_total_shots": combined_pistol.get("pistol_total_shots", 0),
            "starter_pistol_first_bullet_moving_pct": combined_starter.get("first_bullet_moving_pct"),
            "starter_pistol_shots_while_moving_pct": combined_starter.get("shots_while_moving_pct"),
            "force_pistol_shots_while_moving_pct": combined_force.get("shots_while_moving_pct"),
            "deagle_first_bullet_moving_pct": combined_deagle.get("first_bullet_moving_pct"),
        })
        smg_commentary = _generate_smg_commentary({
            "smg_metrics_confidence": combined_smg.get("smg_metrics_confidence", "none"),
            "smg_shots_while_moving_pct": combined_smg.get("smg_shots_while_moving_pct"),
        })
        rifle_commentary = _generate_rifle_commentary(combined_rifle, combined_ak, combined_m4)

        aggregated["mechanics"] = {
            "reliable": True,
            "rifle_reliable": bool(combined_rifle.get("rifle_reliable")),
            "pistol_reliable": bool(combined_pistol.get("pistol_reliable")),
            "smg_reliable": bool(combined_smg.get("smg_reliable")),
            "metrics_confidence": combined_rifle.get("rifle_metrics_confidence", "medium"),
            "rifle_metrics_confidence": combined_rifle.get("rifle_metrics_confidence", "none"),
            "pistol_metrics_confidence": combined_pistol.get("pistol_metrics_confidence", "none"),
            "smg_metrics_confidence": combined_smg.get("smg_metrics_confidence", "none"),
            "combined_rifle": combined_rifle,
            "combined_pistol": combined_pistol,
            "combined_smg": combined_smg,
            "combined_general": combined_general,
            "combined_ak": combined_ak,
            "combined_m4": combined_m4,
            "combined_starter_pistol": combined_starter,
            "combined_force_pistol": combined_force,
            "combined_deagle": combined_deagle,
            "combined_revolver": combined_revolver,
            "counter_strafe_commentary": rifle_commentary,
            "rifle_commentary": rifle_commentary,
            "pistol_commentary": pistol_commentary,
            "smg_commentary": smg_commentary,
            "shots_with_velocity": sum(m.get("shots_with_velocity", 0) for m in reliable_mech),
            "total_shots": sum(m.get("total_shots", 0) for m in reliable_mech),
            "rifle_total_shots": combined_rifle.get("rifle_total_shots", 0),
            "rifle_shots_with_velocity": combined_rifle.get("rifle_shots_with_velocity", 0),
            "rifle_shots_while_moving_pct": combined_rifle.get("rifle_shots_while_moving_pct"),
            "rifle_first_bullet_moving_pct": combined_rifle.get("rifle_first_bullet_moving_pct"),
            "rifle_average_speed_at_shot": combined_rifle.get("rifle_average_speed_at_shot"),
            "rifle_median_speed_at_shot": _avg("rifle_median_speed_at_shot"),
            "rifle_spray_length_average": combined_rifle.get("rifle_spray_length_average"),
            "rifle_long_spray_pct": combined_rifle.get("rifle_long_spray_pct"),
            "pistol_total_shots": combined_pistol.get("pistol_total_shots", 0),
            "pistol_shots_with_velocity": combined_pistol.get("pistol_shots_with_velocity", 0),
            "pistol_average_speed_at_shot": combined_pistol.get("pistol_average_speed_at_shot"),
            "pistol_median_speed_at_shot": _avg("pistol_median_speed_at_shot"),
            "pistol_shots_while_moving_pct": combined_pistol.get("pistol_shots_while_moving_pct"),
            "pistol_first_bullet_moving_pct": combined_pistol.get("pistol_first_bullet_moving_pct"),
            "pistol_spam_length_average": combined_pistol.get("pistol_spray_length_average"),
            "pistol_long_spam_pct": combined_pistol.get("pistol_long_spray_pct"),
            "starter_pistol_total_shots": combined_starter.get("total_shots", 0),
            "starter_pistol_first_bullet_moving_pct": combined_starter.get("first_bullet_moving_pct"),
            "starter_pistol_shots_while_moving_pct": combined_starter.get("shots_while_moving_pct"),
            "force_pistol_total_shots": combined_force.get("total_shots", 0),
            "force_pistol_first_bullet_moving_pct": combined_force.get("first_bullet_moving_pct"),
            "force_pistol_shots_while_moving_pct": combined_force.get("shots_while_moving_pct"),
            "deagle_total_shots": combined_deagle.get("total_shots", 0),
            "deagle_first_bullet_moving_pct": combined_deagle.get("first_bullet_moving_pct"),
            "smg_total_shots": combined_smg.get("smg_total_shots", 0),
            "smg_shots_with_velocity": combined_smg.get("smg_shots_with_velocity", 0),
            "smg_shots_while_moving_pct": combined_smg.get("smg_shots_while_moving_pct"),
            "smg_first_bullet_moving_pct": combined_smg.get("smg_first_bullet_moving_pct"),
            "smg_spray_length_average": combined_smg.get("smg_spray_length_average"),
            "smg_long_spray_pct": combined_smg.get("smg_long_spray_pct"),
            "burst_count": sum(m.get("burst_count", 0) for m in reliable_mech),
            "shots_while_moving_pct": combined_general.get("shots_while_moving_pct"),
            "first_bullet_moving_pct": combined_general.get("first_bullet_moving_pct"),
            "average_speed_at_shot": combined_general.get("average_speed_at_shot"),
            "median_speed_at_shot": _avg("median_speed_at_shot"),
            "spray_length_average": combined_general.get("spray_length_average"),
            "long_spray_pct": combined_general.get("long_spray_pct"),
            "weapon_shot_counts": weapon_totals,
            "ak_m4_shot_counts": ak_totals,
            "ak_metrics": combined_ak,
            "m4_metrics": combined_m4,
            "commentary": rifle_commentary,
            "note": (
                f"{len(reliable_mech)} demo combined — ana yorum rifle/pistol/SMG ayrı metriklerle üretildi."
            ),
            "proper_counter_strafe_v2": combine_proper_counter_strafe_v2(
                [
                    (d.get("proper_counter_strafe_v2") or d.get("mechanics", {}).get("proper_counter_strafe_v2") or {})
                    for d in ok_demos
                ]
            ),
            "legacy_metric_label": "legacy_first_bullet_moving",
        }

    # Always attach V2 (even when legacy velocity metrics are unreliable).
    v2_combined = combine_proper_counter_strafe_v2(
        [
            (d.get("proper_counter_strafe_v2") or d.get("mechanics", {}).get("proper_counter_strafe_v2") or {})
            for d in ok_demos
        ]
    )
    aggregated["mechanics"]["proper_counter_strafe_v2"] = v2_combined
    aggregated["mechanics"]["legacy_metric_label"] = "legacy_first_bullet_moving"
    aggregated["proper_counter_strafe_v2"] = v2_combined

    aggregated["per_demo_cards"] = per_demo_cards

    all_weapons: dict[str, int] = {}
    for d in ok_demos:
        for entry in d.get("weapons") or []:
            if "(" in entry:
                name, _, count = entry.partition(" (")
                count = count.rstrip(")")
                try:
                    all_weapons[name] = all_weapons.get(name, 0) + int(count)
                except ValueError:
                    pass
    aggregated["weapons"] = [f"{w} ({c})" for w, c in sorted(all_weapons.items(), key=lambda x: -x[1])[:10]]

    round_vals = [d.get("round_count") for d in ok_demos if d.get("round_count")]
    if round_vals:
        aggregated["round_count"] = max(round_vals)

    confidence = "none"
    if ok_demos:
        confs = [
            d.get("mechanics", {}).get("metrics_confidence", "none")
            for d in ok_demos
        ]
        if "medium" in confs:
            confidence = "medium"
        elif "low" in confs:
            confidence = "low"
        elif any(d.get("player_matched") for d in ok_demos):
            confidence = "low"

    player_matched = any(d.get("player_matched") for d in ok_demos)
    matched_names = [d.get("matched_name") for d in ok_demos if d.get("matched_name")]

    status = "ok" if ok_demos else "unavailable"
    reason = ""
    if not ok_demos:
        if extraction_failed and not parseable:
            reason = extraction_failed[0].get("error", "Demo çıkarılamadı.")
        elif unavailable_demos:
            reason = unavailable_demos[0].get("reason", "Demo okunamadı.")
        elif not demoparser_available():
            reason = "demoparser2 kurulu değil."
        elif not parseable:
            reason = "Parse edilebilir demo yok."
        else:
            reason = "Parser denemesi başarısız."

    parser_result = "başarılı" if ok_demos else (
        "başarısız" if parser_attempted else "denenmedi"
    )

    parseable_list = preparation.get("parseable") or parseable
    logical_demo_count = len(parseable_list) if parseable_list else len(demo_files)

    return {
        "status": status,
        "reason": reason,
        "demo_count": logical_demo_count,
        "confidence": confidence,
        "folder": str(demo_folder.resolve()),
        "nickname": nickname,
        "parser": "demoparser2" if demoparser_available() else "none",
        "found_count": logical_demo_count,
        "raw_file_count": len(demo_files),
        "parsed_count": len(ok_demos),
        "compressed_count": len(compressed),
        "compressed_found": bool(compressed),
        "compressed_note": compressed_note,
        "extractions": extractions,
        "parser_attempted": parser_attempted,
        "parser_result": parser_result,
        "mechanics_produced": mechanics_produced,
        "player_matched": player_matched,
        "matched_name": matched_names[0] if matched_names else None,
        "demos": parsed_demos,
        "aggregated": aggregated,
        "per_demo_cards": per_demo_cards,
    }
