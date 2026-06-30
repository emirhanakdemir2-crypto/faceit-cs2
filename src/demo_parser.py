from __future__ import annotations

import gzip
import re
import shutil
from pathlib import Path
from typing import Any

from src.config import MISSING_DATA_LABEL

DEMO_EXTENSIONS = (".dem", ".dem.gz", ".dem.zst")
COMPRESSED_EXTENSIONS = (".dem.gz", ".dem.zst")
MATCH_ID_RE = re.compile(
    r"1-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)
MOVING_SPEED_THRESHOLD = 34.0
MIN_SHOTS_FOR_METRICS = 20
SPRAY_GAP_TICKS = 16


def demoparser_available() -> bool:
    try:
        import demoparser2  # noqa: F401

        return True
    except ImportError:
        return False


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
    return name.endswith(".dem") and not name.endswith(".dem.gz") and not name.endswith(".dem.zst")


def _decompressed_dem_path(compressed_path: Path) -> Path:
    name = compressed_path.name
    lower = name.lower()
    if lower.endswith(".dem.zst"):
        return compressed_path.with_name(name[:-4])
    if lower.endswith(".dem.gz"):
        return compressed_path.with_name(name[:-3])
    return compressed_path


def extract_compressed_demo(compressed_path: Path) -> dict[str, Any]:
    """Sıkıştırılmış .dem.zst / .dem.gz dosyasını aynı klasöre .dem olarak çıkarır."""
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
        if name_lower.endswith(".dem.zst"):
            try:
                import zstandard as zstd
            except ImportError:
                result["error"] = "zstandard kurulu değil. pip install zstandard"
                return result
            dctx = zstd.ZstdDecompressor()
            with compressed_path.open("rb") as f_in, out_path.open("wb") as f_out:
                dctx.copy_stream(f_in, f_out)
        elif name_lower.endswith(".dem.gz"):
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
    """Demo klasöründeki .dem / .dem.gz / .dem.zst dosyalarını listeler."""
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


def _resolve_player_names(player_info: Any, nickname: str) -> tuple[bool, str | None, list[str]]:
    nick = nickname.strip().lower()
    all_names: list[str] = []
    matched_name: str | None = None

    for row in _df_records(player_info):
        for key in ("name", "player_name", "playerName"):
            val = row.get(key)
            if val:
                all_names.append(str(val))
                name_lower = str(val).lower()
                if nick == name_lower or nick in name_lower or name_lower in nick:
                    matched_name = str(val)

    return matched_name is not None, matched_name, all_names


def _row_player_name(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        val = row.get(key)
        if val not in (None, ""):
            return str(val)
    return None


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
) -> dict[str, Any]:
    """weapon_fire eventlerini çıkarmayı dener."""
    result: dict[str, Any] = {
        "available": False,
        "shot_count": 0,
        "rows": [],
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
            player=["X", "Y", "velocity", "name"],
            other=["weapon"],
        )
        rows = _df_records(df)
        if not rows:
            result["reason"] = "weapon_fire eventi boş döndü."
            return result

        target = (matched_name or nickname).strip().lower()
        nick = nickname.strip().lower()
        filtered: list[dict[str, Any]] = []
        for row in rows:
            pname = _row_player_name(row, "name", "player_name")
            if not pname:
                filtered.append(row)
                continue
            pl = pname.lower()
            if pl == target or nick in pl or pl in nick:
                filtered.append(row)

        player_rows = filtered if filtered else rows
        result["available"] = len(player_rows) > 0
        result["shot_count"] = len(player_rows)
        result["rows"] = player_rows
        if not result["available"]:
            result["reason"] = "Oyuncuya ait shot event bulunamadı."
    except Exception as exc:
        result["reason"] = f"Shot event çıkarılamadı: {exc}"

    return result


def extract_player_ticks_if_available(parser: Any, matched_name: str | None) -> dict[str, Any]:
    """Tick/velocity verisinin erişilebilirliğini kontrol eder."""
    result: dict[str, Any] = {
        "available": False,
        "tick_count": 0,
        "reason": "",
    }
    try:
        kwargs: dict[str, Any] = {}
        if matched_name:
            kwargs["players"] = [matched_name]
        df = parser.parse_ticks(["X", "Y", "velocity", "name"], **kwargs)
        rows = _df_records(df)
        result["tick_count"] = len(rows)
        result["available"] = len(rows) > 0
        if not result["available"]:
            result["reason"] = "Tick verisi boş döndü."
    except Exception as exc:
        result["reason"] = f"Tick verisi alınamadı: {exc}"
    return result


def _speed_from_row(row: dict[str, Any]) -> float | None:
    vel = row.get("velocity")
    if isinstance(vel, (list, tuple)) and len(vel) >= 2:
        try:
            return (float(vel[0]) ** 2 + float(vel[1]) ** 2) ** 0.5
        except (TypeError, ValueError):
            return None
    for key in ("speed", "velocity_length"):
        if key in row and row[key] is not None:
            try:
                return float(row[key])
            except (TypeError, ValueError):
                pass
    return None


def _compute_shot_mechanics(shot_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Shot + velocity satırlarından ilk mekanik metrikleri hesaplar."""
    speeds: list[float] = []
    moving_shots = 0
    first_bullet_moving = 0
    burst_groups = 0
    burst_lengths: list[int] = []
    weapon_counts: dict[str, int] = {}
    rows_with_speed = 0

    current_burst = 0
    prev_tick: int | None = None

    for row in shot_rows:
        speed = _speed_from_row(row)
        weapon = _row_player_name(row, "weapon", "weapon_name") or "unknown"
        weapon_counts[weapon] = weapon_counts.get(weapon, 0) + 1

        tick_val = row.get("tick")
        try:
            tick = int(tick_val) if tick_val is not None else None
        except (TypeError, ValueError):
            tick = None

        if speed is not None:
            rows_with_speed += 1
            speeds.append(speed)
            if speed > MOVING_SPEED_THRESHOLD:
                moving_shots += 1
                if current_burst == 0:
                    first_bullet_moving += 1

        if tick is not None and prev_tick is not None and tick - prev_tick <= SPRAY_GAP_TICKS:
            current_burst += 1
        else:
            if current_burst > 0:
                burst_groups += 1
                burst_lengths.append(current_burst + 1)
            current_burst = 0
        prev_tick = tick

    if current_burst > 0:
        burst_groups += 1
        burst_lengths.append(current_burst + 1)

    total_shots = len(shot_rows)
    reliable = rows_with_speed >= MIN_SHOTS_FOR_METRICS

    metrics: dict[str, Any] = {
        "reliable": reliable,
        "shots_while_moving_pct": MISSING_DATA_LABEL,
        "first_bullet_moving_pct": MISSING_DATA_LABEL,
        "average_speed_at_shot": MISSING_DATA_LABEL,
        "spray_length_average": MISSING_DATA_LABEL,
        "weapon_shot_counts": weapon_counts,
        "note": "",
    }

    if not reliable:
        metrics["note"] = (
            "Bu demoda shot + velocity eşleşmesi güvenilir çıkarılamadı."
        )
        return metrics

    metrics["shots_while_moving_pct"] = round(moving_shots / rows_with_speed * 100, 1)
    metrics["first_bullet_moving_pct"] = round(first_bullet_moving / total_shots * 100, 1)
    metrics["average_speed_at_shot"] = round(sum(speeds) / len(speeds), 1)
    if burst_lengths:
        metrics["spray_length_average"] = round(sum(burst_lengths) / len(burst_lengths), 1)
    metrics["note"] = (
        f"{rows_with_speed} shot üzerinden ön metrik hesaplandı; kesin teşhis için daha fazla demo gerekir."
    )
    return metrics


def parse_demo_basic(demo_path: str | Path, nickname: str) -> dict[str, Any]:
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
        matched, matched_name, all_names = _resolve_player_names(player_info, nickname)

        death_df = None
        events = []
        try:
            events = parser.list_game_events()
        except Exception:
            events = []

        if "player_death" in events:
            death_df = parser.parse_event(
                "player_death",
                player=["X", "Y"],
                other=["weapon", "total_rounds_played"],
            )

        death_rows = _df_records(death_df)
        kd = extract_kill_death_events(death_rows, matched_name, nickname)
        shots = extract_shot_events_if_available(parser, matched_name, nickname)
        ticks = extract_player_ticks_if_available(parser, matched_name)

        mechanics: dict[str, Any] = {
            "reliable": False,
            "note": "Bu demoda shot + velocity eşleşmesi güvenilir çıkarılamadı.",
        }
        if shots.get("available") and shots.get("rows"):
            mechanics = _compute_shot_mechanics(shots["rows"])

        confidence = "none"
        if matched and kd["kills"] + kd["deaths"] > 0:
            confidence = "low"
        if mechanics.get("reliable"):
            confidence = "medium"

        return {
            **base,
            "status": "ok",
            "reason": "",
            "demo_count": 1,
            "confidence": confidence,
            "parser_status": "ok",
            "player_matched": matched,
            "matched_name": matched_name,
            "players_in_demo": all_names[:20],
            "kills": kd["kills"],
            "deaths": kd["deaths"],
            "weapons": kd["weapons"],
            "round_count": kd["round_count"],
            "tick_data_available": ticks.get("available", False),
            "tick_data_note": ticks.get("reason") or (
                f"{ticks.get('tick_count', 0)} tick okundu." if ticks.get("available") else "veri yetersiz"
            ),
            "shot_event_available": shots.get("available", False),
            "shot_event_note": shots.get("reason") or (
                f"{shots.get('shot_count', 0)} shot event okundu."
                if shots.get("available") else "veri yetersiz"
            ),
            "mechanics": mechanics,
            "events_found": events[:15],
        }
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
    mechanics_produced = any(d.get("mechanics", {}).get("reliable") for d in ok_demos)

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
        "tick_data_available": any(d.get("tick_data_available") for d in ok_demos),
        "shot_event_available": any(d.get("shot_event_available") for d in ok_demos),
        "mechanics": {
            "reliable": False,
            "note": "Bu demoda shot + velocity eşleşmesi güvenilir çıkarılamadı.",
        },
    }

    reliable_mech = [d.get("mechanics", {}) for d in ok_demos if d.get("mechanics", {}).get("reliable")]
    if reliable_mech:
        def _avg(key: str) -> float | str:
            vals = [m[key] for m in reliable_mech if isinstance(m.get(key), (int, float))]
            return round(sum(vals) / len(vals), 1) if vals else MISSING_DATA_LABEL

        weapon_totals: dict[str, int] = {}
        for m in reliable_mech:
            for w, c in (m.get("weapon_shot_counts") or {}).items():
                weapon_totals[w] = weapon_totals.get(w, 0) + int(c)

        aggregated["mechanics"] = {
            "reliable": True,
            "shots_while_moving_pct": _avg("shots_while_moving_pct"),
            "first_bullet_moving_pct": _avg("first_bullet_moving_pct"),
            "average_speed_at_shot": _avg("average_speed_at_shot"),
            "spray_length_average": _avg("spray_length_average"),
            "weapon_shot_counts": weapon_totals,
            "note": (
                f"{len(reliable_mech)} demo üzerinden ön metrik ortalaması; "
                "kesin counter-strafe/spray teşhisi için daha fazla doğrulama gerekir."
            ),
        }

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
        confidence = "low"
    if any(d.get("player_matched") for d in ok_demos):
        confidence = "low" if not reliable_mech else "medium"

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

    return {
        "status": status,
        "reason": reason,
        "demo_count": len(demo_files),
        "confidence": confidence,
        "folder": str(demo_folder.resolve()),
        "nickname": nickname,
        "parser": "demoparser2" if demoparser_available() else "none",
        "found_count": len(demo_files),
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
    }
