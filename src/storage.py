from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from src.config import DB_PATH, MISSING_DATA_LABEL


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
                nickname TEXT PRIMARY KEY,
                player_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS matches (
                match_id TEXT NOT NULL,
                nickname TEXT NOT NULL,
                map_name TEXT,
                result TEXT,
                kills INTEGER,
                deaths INTEGER,
                assists INTEGER,
                adr REAL,
                hs_percent REAL,
                kast REAL,
                elo INTEGER,
                played_at TEXT,
                raw_json_path TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (match_id, nickname)
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nickname TEXT NOT NULL,
                created_at TEXT NOT NULL,
                total_matches INTEGER,
                new_matches_count INTEGER,
                win_rate REAL,
                kd REAL,
                adr REAL,
                hs_percent REAL,
                kast REAL,
                best_map TEXT,
                worst_map TEXT,
                report_path TEXT
            );

            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER,
                nickname TEXT NOT NULL,
                problem_area TEXT,
                recommendation TEXT,
                target_metric TEXT,
                status TEXT DEFAULT 'open',
                created_at TEXT NOT NULL,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id)
            );
            """
        )
        _migrate_schema(conn)


def _migrate_schema(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(analyses)")}
    for name, col_type in (
        ("days", "INTEGER"),
        ("requested_matches", "INTEGER"),
        ("analyzed_matches", "INTEGER"),
        ("match_ids_json", "TEXT"),
        ("period_metrics_json", "TEXT"),
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE analyses ADD COLUMN {name} {col_type}")


def upsert_player(nickname: str, player_id: str | None) -> None:
    now = _now_iso()
    with _connect() as conn:
        row = conn.execute(
            "SELECT nickname FROM players WHERE nickname = ?",
            (nickname.lower(),),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE players SET player_id = ?, updated_at = ? WHERE nickname = ?",
                (player_id, now, nickname.lower()),
            )
        else:
            conn.execute(
                "INSERT INTO players (nickname, player_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (nickname.lower(), player_id, now, now),
            )


def get_known_match_ids(nickname: str) -> set[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT match_id FROM matches WHERE nickname = ?",
            (nickname.lower(),),
        ).fetchall()
    return {row["match_id"] for row in rows}


def count_stored_matches(nickname: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM matches WHERE nickname = ?",
            (nickname.lower(),),
        ).fetchone()
    return int(row["cnt"]) if row else 0


def save_match(nickname: str, match: dict[str, Any], raw_json_path: str | None = None) -> None:
    match_id = match.get("match_id")
    if not match_id or match_id == MISSING_DATA_LABEL:
        return

    won = match.get("won")
    if won is True:
        result = "win"
    elif won is False:
        result = "loss"
    else:
        result = "unknown"

    def _num(field: str) -> float | None:
        val = match.get(field)
        if val is None or val == MISSING_DATA_LABEL:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _int(field: str) -> int | None:
        val = match.get(field)
        if val is None or val == MISSING_DATA_LABEL:
            return None
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return None

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO matches (
                match_id, nickname, map_name, result, kills, deaths, assists,
                adr, hs_percent, kast, elo, played_at, raw_json_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id, nickname) DO UPDATE SET
                map_name = excluded.map_name,
                result = excluded.result,
                kills = excluded.kills,
                deaths = excluded.deaths,
                assists = excluded.assists,
                adr = excluded.adr,
                hs_percent = excluded.hs_percent,
                kast = excluded.kast,
                played_at = excluded.played_at,
                raw_json_path = excluded.raw_json_path
            """,
            (
                match_id,
                nickname.lower(),
                match.get("map"),
                result,
                _int("kills"),
                _int("deaths"),
                _int("assists"),
                _num("adr"),
                _num("headshot_pct"),
                _num("kast"),
                None,
                match.get("finished_at"),
                raw_json_path,
                _now_iso(),
            ),
        )


def get_last_analysis(nickname: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM analyses
            WHERE nickname = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (nickname.lower(),),
        ).fetchone()
    return dict(row) if row else None


def get_previous_analysis_before_current(nickname: str) -> dict[str, Any] | None:
    """Mevcut kayıt öncesi son analizi döndürür (ikinci en son)."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM analyses
            WHERE nickname = ?
            ORDER BY id DESC
            LIMIT 1 OFFSET 1
            """,
            (nickname.lower(),),
        ).fetchone()
    return dict(row) if row else None


def save_analysis(
    nickname: str,
    *,
    total_matches: int,
    new_matches_count: int,
    summary: dict[str, Any],
    map_stats: dict[str, Any],
    report_path: str,
    days: int = 90,
    requested_matches: int = 120,
    analyzed_matches: int = 0,
    match_ids: list[str] | None = None,
    period_metrics: dict[str, Any] | None = None,
) -> int:
    def _num(val: Any) -> float | None:
        if val is None or val == MISSING_DATA_LABEL:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO analyses (
                nickname, created_at, total_matches, new_matches_count,
                win_rate, kd, adr, hs_percent, kast, best_map, worst_map, report_path,
                days, requested_matches, analyzed_matches, match_ids_json, period_metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nickname.lower(),
                _now_iso(),
                total_matches,
                new_matches_count,
                _num(summary.get("win_rate_pct")),
                _num(summary.get("avg_kd_ratio")),
                _num(summary.get("avg_adr")),
                _num(summary.get("avg_headshot_pct")),
                _num(summary.get("avg_kast")),
                map_stats.get("best_map"),
                map_stats.get("worst_map"),
                report_path,
                days,
                requested_matches,
                analyzed_matches or total_matches,
                json.dumps(match_ids or []),
                json.dumps(period_metrics or {}),
            ),
        )
        return int(cursor.lastrowid)


def save_recommendations(
    analysis_id: int,
    nickname: str,
    items: list[dict[str, str]],
) -> None:
    now = _now_iso()
    with _connect() as conn:
        for item in items:
            conn.execute(
                """
                INSERT INTO recommendations (
                    analysis_id, nickname, problem_area, recommendation,
                    target_metric, status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'open', ?)
                """,
                (
                    analysis_id,
                    nickname.lower(),
                    item.get("problem_area", ""),
                    item.get("recommendation", ""),
                    item.get("target_metric", ""),
                    now,
                ),
            )


def get_open_recommendations(nickname: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM recommendations
            WHERE nickname = ? AND status = 'open'
            ORDER BY id DESC
            """,
            (nickname.lower(),),
        ).fetchall()
    return [dict(r) for r in rows]


def update_recommendation_status(rec_id: int, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE recommendations SET status = ? WHERE id = ?",
            (status, rec_id),
        )


def _metric_delta(current: Any, previous: Any, *, higher_is_better: bool = True) -> str | None:
    if current is None or previous is None:
        return None
    if current == MISSING_DATA_LABEL or previous == MISSING_DATA_LABEL:
        return None
    try:
        c, p = float(current), float(previous)
    except (TypeError, ValueError):
        return None
    diff = c - p
    if abs(diff) < 0.01:
        return "unchanged"
    if higher_is_better:
        return "improved" if diff > 0 else "worsened"
    return "improved" if diff < 0 else "worsened"


def evaluate_recommendations(
    nickname: str,
    summary: dict[str, Any],
    previous_analysis: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Önceki önerilerin durumunu günceller ve listeler."""
    if not previous_analysis:
        return []

    metric_map = {
        "win_rate": ("win_rate_pct", True),
        "kd": ("avg_kd_ratio", True),
        "adr": ("avg_adr", True),
        "hs_percent": ("avg_headshot_pct", True),
        "kast": ("avg_kast", True),
    }

    results: list[dict[str, Any]] = []
    open_recs = get_open_recommendations(nickname)

    for rec in open_recs:
        target = rec.get("target_metric", "")
        field, higher = metric_map.get(target, (None, True))
        status = "unchanged"
        if field:
            delta = _metric_delta(
                summary.get(field),
                previous_analysis.get(target.replace("avg_", "").replace("_ratio", "")),
            )
            # previous analysis stores win_rate, kd, adr directly
            prev_val = previous_analysis.get(target)
            if target == "win_rate":
                prev_val = previous_analysis.get("win_rate")
            elif target == "kd":
                prev_val = previous_analysis.get("kd")
            elif target == "adr":
                prev_val = previous_analysis.get("adr")
            elif target == "hs_percent":
                prev_val = previous_analysis.get("hs_percent")
            elif target == "kast":
                prev_val = previous_analysis.get("kast")

            curr_val = summary.get(field) if field else None
            if field == "win_rate_pct":
                curr_val = summary.get("win_rate_pct")
                prev_val = previous_analysis.get("win_rate")

            delta = _metric_delta(curr_val, prev_val, higher_is_better=higher)
            if delta == "improved":
                status = "gelişti"
                update_recommendation_status(rec["id"], "improved")
            elif delta == "worsened":
                status = "kötüleşti"
                update_recommendation_status(rec["id"], "worsened")
            else:
                status = "değişmedi"

        results.append(
            {
                "problem_area": rec.get("problem_area"),
                "recommendation": rec.get("recommendation"),
                "target_metric": target,
                "status": status,
            }
        )

    return results


def build_memory_context(
    nickname: str,
    summary: dict[str, Any],
    map_stats: dict[str, Any],
    new_match_ids: list[str],
    fetched_match_ids: list[str],
    coaching_focus: list[str],
    report_path: str,
    *,
    previous: dict[str, Any] | None = None,
    pistol_metrics_sufficient: bool = False,
) -> dict[str, Any]:
    """Hafıza tabanlı rapor bağlamını oluşturur."""
    stored_total = count_stored_matches(nickname)
    is_first = previous is None
    new_count = len(new_match_ids)

    if is_first:
        status_message = (
            "İlk analiz oluşturuldu. Bu rapor bundan sonraki analizler için baseline olacak."
        )
    elif new_count == 0:
        status_message = "Son analizden sonra yeni maç bulunamadı."
    else:
        status_message = f"Son analizden bu yana {new_count} yeni maç tespit edildi."

    improved: list[str] = []
    worsened: list[str] = []
    unchanged_problems: list[str] = []

    if previous:
        prev_period: dict[str, Any] = {}
        raw_period = previous.get("period_metrics_json")
        if raw_period:
            try:
                prev_period = json.loads(raw_period)
            except json.JSONDecodeError:
                prev_period = {}

        comparisons = [
            ("Kazanma oranı", "win_rate_pct", "win_rate", True, 3.0),
            ("K/D", "avg_kd_ratio", "kd", True, 0.05),
            ("ADR", "avg_adr", "adr", True, 3.0),
            ("Headshot %", "avg_headshot_pct", "hs_percent", True, 2.0),
            ("KAST", "avg_kast", "kast", True, 2.0),
        ]
        for label, curr_key, prev_key, _hb, threshold in comparisons:
            try:
                curr = summary.get(curr_key)
                prev = previous.get(prev_key)
                if curr in (None, MISSING_DATA_LABEL) or prev is None:
                    continue
                c, p = float(curr), float(prev)
                diff = c - p
                if abs(diff) < threshold:
                    if label == "Kazanma oranı" and c < 45:
                        unchanged_problems.append(f"{label} hâlâ düşük ({c}%)")
                    elif label == "K/D" and c < 1.0:
                        unchanged_problems.append(f"{label} hâlâ düşük ({c})")
                    continue
                if diff > 0:
                    improved.append(f"{label}: {p} → {c}")
                else:
                    worsened.append(f"{label}: {p} → {c}")
            except (TypeError, ValueError):
                continue

        if prev_period:
            prev_last = prev_period.get("last_30_days", {}).get("summary", {})
            curr_last_wr = summary.get("win_rate_pct")
            try:
                if prev_last and curr_last_wr not in (None, MISSING_DATA_LABEL):
                    plwr = prev_last.get("win_rate_pct")
                    if plwr not in (None, MISSING_DATA_LABEL):
                        diff = float(curr_last_wr) - float(plwr)
                        if abs(diff) >= 5:
                            tag = "yükseldi" if diff > 0 else "düştü"
                            improved.append(
                                f"Son 30 gün kazanma oranı önceki analize göre {tag}."
                            )
            except (TypeError, ValueError):
                pass

        if not improved:
            improved.append("Belirgin iyileşme tespit edilmedi.")
        if not worsened:
            worsened.append("Belirgin kötüleşme tespit edilmedi.")
        if not unchanged_problems:
            unchanged_problems.append("Önceki analizdeki problemler büyük ölçüde değişti veya veri yetersiz.")

    focus_plan = _build_7_day_plan(
        coaching_focus,
        pistol_metrics_sufficient=pistol_metrics_sufficient,
    )

    return {
        "is_first_analysis": is_first,
        "status_message": status_message,
        "stored_matches_total": stored_total,
        "new_matches_count": new_count,
        "new_match_ids": new_match_ids,
        "fetched_match_ids": fetched_match_ids,
        "previous_analysis_date": previous.get("created_at") if previous else None,
        "improved_areas": improved,
        "worsened_areas": worsened,
        "unchanged_problems": unchanged_problems,
        "focus_plan_7d": focus_plan,
        "report_path": report_path,
    }


def _build_7_day_plan(
    focus_items: list[str] | None = None,
    *,
    pistol_metrics_sufficient: bool = False,
) -> list[dict[str, str]]:
    """Mekanik odaklı sabit 7 günlük plan."""
    days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    day5 = (
        "Pistol mechanics — starter/force pistol ADAD ve ilk mermi reset"
        if pistol_metrics_sufficient
        else "Utility + default setup review (pistol demo verisi yetersiz)"
    )
    focuses = [
        "AK counter-strafe + 1–3 bullet tap (DM/warmup)",
        "M4 5 bullet burst + spray reset drill",
        "Dust2 demo review — pozisyon ve rotasyon",
        "Ancient/Anubis pozisyon review",
        day5,
        "1–2 FACEIT maç + demo çıkar",
        "Yeni demo ile metrik karşılaştırması (Mechanics Lab)",
    ]
    return [{"day": day, "focus": focus} for day, focus in zip(days, focuses)]


def persist_analysis_run(
    nickname: str,
    player_id: str | None,
    matches: list[dict[str, Any]],
    summary: dict[str, Any],
    map_stats: dict[str, Any],
    coaching: dict[str, Any],
    report_path: str,
    known_before: set[str],
    *,
    days: int = 90,
    requested_matches: int = 120,
    period_metrics: dict[str, Any] | None = None,
    mechanics_lab: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Maçları kaydeder, analiz ve önerileri persist eder."""
    previous = get_last_analysis(nickname)
    upsert_player(nickname, player_id)

    new_match_ids: list[str] = []
    fetched_ids: list[str] = []

    for match in matches:
        mid = match.get("match_id")
        if not mid or mid == MISSING_DATA_LABEL:
            continue
        fetched_ids.append(mid)
        if mid not in known_before:
            new_match_ids.append(mid)
        raw_path = f"data/raw/matches/{mid}_stats.json"
        save_match(nickname, match, raw_json_path=raw_path)

    focus_items: list[str] = []
    rec_items: list[dict[str, str]] = []
    for section in coaching.get("sections") or []:
        if section.get("title") == "Öncelikli Çalışma Alanları":
            focus_items = section.get("items") or []
        if section.get("title") == "Geliştirilmesi Gerekenler":
            for item in section.get("items") or []:
                rec_items.append(
                    {
                        "problem_area": item[:80],
                        "recommendation": item,
                        "target_metric": _guess_target_metric(item),
                    }
                )

    rec_status = evaluate_recommendations(nickname, summary, previous) if previous else []

    pistol_ok = False
    if mechanics_lab:
        mech = (mechanics_lab.get("aggregated") or {}).get("mechanics") or {}
        pistol_total = mech.get("pistol_total_shots", 0) or 0
        pistol_conf = mech.get("pistol_metrics_confidence", "none")
        pistol_ok = pistol_total >= 10 and pistol_conf != "none"

    memory = build_memory_context(
        nickname,
        summary,
        map_stats,
        new_match_ids,
        fetched_ids,
        focus_items,
        report_path,
        previous=previous,
        pistol_metrics_sufficient=pistol_ok,
    )
    memory["recommendation_status"] = rec_status

    analysis_id = save_analysis(
        nickname,
        total_matches=summary.get("total_matches", 0),
        new_matches_count=len(new_match_ids),
        summary=summary,
        map_stats=map_stats,
        report_path=report_path,
        days=days,
        requested_matches=requested_matches,
        analyzed_matches=len(fetched_ids),
        match_ids=fetched_ids,
        period_metrics=period_metrics,
    )

    if rec_items:
        save_recommendations(analysis_id, nickname, rec_items[:5])

    return memory


def _guess_target_metric(text: str) -> str:
    lower = text.lower()
    if "kazanma" in lower or "win" in lower:
        return "win_rate"
    if "adr" in lower or "hasar" in lower:
        return "adr"
    if "k/d" in lower or "kd" in lower:
        return "kd"
    if "headshot" in lower or "aim" in lower:
        return "hs_percent"
    if "kast" in lower:
        return "kast"
    return "win_rate"
