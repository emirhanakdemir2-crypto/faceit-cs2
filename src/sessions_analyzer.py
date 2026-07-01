from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from src import suite_config as cfg
from src.config import MISSING_DATA_LABEL
from src.suite_common import (
    SOURCE_DERIVED,
    SOURCE_FACEIT,
    SOURCE_UNAVAILABLE,
    as_float,
    fmt_simple,
    metric,
)


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(val[:19])
        except ValueError:
            return None


def _group_sessions(matches: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Aynı gün veya 3 saatten az arayla oynanan maçlar = session."""
    sorted_m = sorted(
        [m for m in matches if m.get("finished_at")],
        key=lambda x: x.get("finished_at") or "",
        reverse=True,
    )
    sessions: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    prev_dt: datetime | None = None

    for m in sorted_m:
        dt = _parse_dt(m.get("finished_at"))
        if dt is None:
            continue
        if not current:
            current = [m]
            prev_dt = dt
            continue
        same_day = prev_dt and dt.date() == prev_dt.date()
        gap_ok = prev_dt and abs((prev_dt - dt).total_seconds()) < cfg.SESSION_GAP_HOURS * 3600
        if same_day or gap_ok:
            current.append(m)
        else:
            sessions.append(current)
            current = [m]
        prev_dt = dt
    if current:
        sessions.append(current)
    return sessions


def _session_stats(session: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for m in session if m.get("won") is True)
    losses = sum(1 for m in session if m.get("won") is False)
    kds = [as_float(m.get("kd_ratio")) for m in session]
    kds = [k for k in kds if k is not None]
    adrs = [as_float(m.get("adr")) for m in session]
    adrs = [a for a in adrs if a is not None]
    decided = wins + losses
    wr = round(wins / decided * 100, 1) if decided else None
    avg_kd = round(sum(kds) / len(kds), 2) if kds else None
    avg_adr = round(sum(adrs) / len(adrs), 1) if adrs else None

    first_kd = kds[0] if kds else None
    last_kd = kds[-1] if kds else None
    tilt = False
    fatigue = False
    notes: list[str] = []

    if len(session) >= 2 and first_kd is not None and last_kd is not None:
        if last_kd < first_kd - 0.15:
            notes.append("Session içinde K/D düşüyor.")
            fatigue = True
    if len(session) >= cfg.SESSION_TILT_MATCHES:
        notes.append(f"{len(session)}+ maç üst üste — fatigue riski.")
        fatigue = True
    loss_run = 0
    for m in session:
        if m.get("won") is False:
            loss_run += 1
        else:
            break
    if loss_run >= 2:
        notes.append("Loss sonrası risk artıyor.")
        tilt = True
    if len(kds) >= 3 and kds[-1] < kds[0] - 0.25:
        notes.append("Son maçlarda K/D çöküşü.")

    max_matches = "2"
    if tilt or fatigue:
        max_matches = "1–2"
    if tilt and fatigue:
        max_matches = "1"

    return {
        "date": metric(session[0].get("finished_at", "")[:10], source=SOURCE_FACEIT),
        "matches": metric(len(session), source=SOURCE_FACEIT),
        "record": metric(f"{wins}W-{losses}L", source=SOURCE_FACEIT),
        "winrate": metric(wr, source=SOURCE_FACEIT),
        "avg_kd": metric(avg_kd, source=SOURCE_FACEIT),
        "avg_adr": metric(avg_adr, source=SOURCE_FACEIT),
        "elo_change": metric("unavailable", source=SOURCE_UNAVAILABLE, confidence="none"),
        "first_kd": metric(first_kd, source=SOURCE_FACEIT),
        "last_kd": metric(last_kd, source=SOURCE_FACEIT),
        "tilt_risk": metric(tilt, source=SOURCE_DERIVED),
        "fatigue_risk": metric(fatigue, source=SOURCE_DERIVED),
        "max_matches_recommendation": metric(max_matches, source=SOURCE_DERIVED),
        "notes": notes,
    }


def analyze_sessions(matches: list[dict[str, Any]]) -> dict[str, Any]:
    sessions = _group_sessions(matches)
    analyzed = [_session_stats(s) for s in sessions[:15]]
    latest_notes: list[str] = []
    if analyzed:
        latest_notes = analyzed[0].get("notes") or []
    return {"sessions": analyzed, "latest_notes": latest_notes}


def render_sessions_markdown(section: dict[str, Any]) -> list[str]:
    lines = [
        "## Sessions",
        "",
        "| Date | Matches | W/L | WR% | Avg K/D | Avg ADR | Tilt | Fatigue | Max maç |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in section.get("sessions") or []:
        lines.append(
            f"| {fmt_simple(s.get('date'))} | {fmt_simple(s.get('matches'))} | "
            f"{fmt_simple(s.get('record'))} | {fmt_simple(s.get('winrate'))} | "
            f"{fmt_simple(s.get('avg_kd'))} | {fmt_simple(s.get('avg_adr'))} | "
            f"{fmt_simple(s.get('tilt_risk'))} | {fmt_simple(s.get('fatigue_risk'))} | "
            f"{fmt_simple(s.get('max_matches_recommendation'))} |"
        )
    lines.append("")
    if section.get("latest_notes"):
        lines.append("**Son session yorumu:**")
        lines.append("")
        for n in section["latest_notes"]:
            lines.append(f"- {n}")
        lines.append("")
    return lines
