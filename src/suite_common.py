from __future__ import annotations

from typing import Any

from src.config import MISSING_DATA_LABEL

SOURCE_FACEIT = "FACEIT API"
SOURCE_DEMO = "Uploaded Demo"
SOURCE_DERIVED = "Derived / Estimated"
SOURCE_UNAVAILABLE = "Unavailable"


def metric(
    value: Any,
    *,
    source: str = SOURCE_FACEIT,
    confidence: str = "medium",
) -> dict[str, Any]:
    """Tek metrik paketi: value + source + confidence."""
    if value is None or value == "" or value == MISSING_DATA_LABEL:
        return {
            "value": "unavailable",
            "source": SOURCE_UNAVAILABLE,
            "confidence": "none",
        }
    return {
        "value": value,
        "source": source,
        "confidence": confidence,
    }


def metric_val(m: dict[str, Any] | Any) -> Any:
    if isinstance(m, dict) and "value" in m:
        return m["value"]
    return m


def fmt_metric(m: dict[str, Any] | Any) -> str:
    if isinstance(m, dict):
        v = m.get("value", MISSING_DATA_LABEL)
        src = m.get("source", "")
        conf = m.get("confidence", "")
        if v == "unavailable":
            return "unavailable"
        return f"{v} _(src: {src}, conf: {conf})_"
    if m is None or m == "":
        return MISSING_DATA_LABEL
    return str(m)


def fmt_simple(m: dict[str, Any] | Any) -> str:
    v = metric_val(m)
    if v == "unavailable" or v is None:
        return "unavailable"
    return str(v)


def is_number(val: Any) -> bool:
    try:
        float(val)
        return True
    except (TypeError, ValueError):
        return False


def as_float(val: Any) -> float | None:
    if not is_number(val):
        return None
    return float(val)


def clamp_score(score: float) -> int:
    return max(0, min(100, int(round(score))))
