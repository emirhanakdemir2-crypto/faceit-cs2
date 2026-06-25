from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.config import MISSING_DATA_LABEL
from src.metrics import compute_performance_summary


def _match_ts(match: dict[str, Any]) -> int | None:
    ts = match.get("finished_at_unix")
    if ts is not None:
        try:
            return int(ts)
        except (TypeError, ValueError):
            pass
    return None


def split_matches_into_periods(
    matches: list[dict[str, Any]],
    days: int = 90,
) -> dict[str, Any]:
    """
    90 günlük pencereyi üç 30 günlük dilime böler (eski → yeni).
    Maçlar finished_at_unix ile sıralanır.
    """
    dated = [m for m in matches if _match_ts(m) is not None]
    if not dated:
        return {
            "first_30_days": _empty_period("İlk 30 gün"),
            "middle_30_days": _empty_period("Orta 30 gün"),
            "last_30_days": _empty_period("Son 30 gün"),
            "note": "Tarih bilgisi yetersiz — dönem kıyaslaması yapılamadı.",
        }

    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(days=days)
    period_len = days / 3

    buckets: dict[str, list[dict[str, Any]]] = {
        "first_30_days": [],
        "middle_30_days": [],
        "last_30_days": [],
    }

    for match in dated:
        ts = _match_ts(match)
        if ts is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        if dt < window_start:
            continue
        elapsed_days = (dt - window_start).total_seconds() / 86400
        if elapsed_days < period_len:
            buckets["first_30_days"].append(match)
        elif elapsed_days < period_len * 2:
            buckets["middle_30_days"].append(match)
        else:
            buckets["last_30_days"].append(match)

    result: dict[str, Any] = {}
    labels = {
        "first_30_days": "İlk 30 gün (pencerenin başı)",
        "middle_30_days": "Orta 30 gün",
        "last_30_days": "Son 30 gün (en güncel)",
    }
    for key, label in labels.items():
        subset = buckets[key]
        summary = compute_performance_summary(matches=subset)
        result[key] = {
            "label": label,
            "match_count": len(subset),
            "summary": summary,
        }

    result["note"] = (
        f"Toplam {len(dated)} maç {days} günlük pencerede üç dilime ayrıldı."
    )
    return result


def _empty_period(label: str) -> dict[str, Any]:
    return {
        "label": label,
        "match_count": 0,
        "summary": compute_performance_summary(matches=[]),
    }


def compare_periods(period_data: dict[str, Any]) -> list[str]:
    """Üç dönem arasında basit trend yorumları."""
    insights: list[str] = []
    first = period_data.get("first_30_days", {}).get("summary", {})
    middle = period_data.get("middle_30_days", {}).get("summary", {})
    last = period_data.get("last_30_days", {}).get("summary", {})

    def _f(val: Any) -> float | None:
        if val in (None, MISSING_DATA_LABEL):
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    wr_first, wr_last = _f(first.get("win_rate_pct")), _f(last.get("win_rate_pct"))
    if wr_first is not None and wr_last is not None:
        diff = wr_last - wr_first
        if diff >= 5:
            insights.append(f"Kazanma oranı ilk döneme göre yükseldi ({wr_first}% → {wr_last}%).")
        elif diff <= -5:
            insights.append(f"Kazanma oranı ilk döneme göre düştü ({wr_first}% → {wr_last}%).")

    kd_first, kd_last = _f(first.get("avg_kd_ratio")), _f(last.get("avg_kd_ratio"))
    if kd_first is not None and kd_last is not None:
        diff = kd_last - kd_first
        if diff >= 0.08:
            insights.append(f"K/D son dönemde güçlendi ({kd_first} → {kd_last}).")
        elif diff <= -0.08:
            insights.append(f"K/D son dönemde zayıfladı ({kd_first} → {kd_last}).")

    adr_mid, adr_last = _f(middle.get("avg_adr")), _f(last.get("avg_adr"))
    if adr_mid is not None and adr_last is not None and abs(adr_last - adr_mid) >= 5:
        insights.append(f"ADR orta → son dönem: {adr_mid} → {adr_last}.")

    if not insights:
        insights.append("Üç dönem arasında belirgin trend tespit edilmedi.")
    return insights
