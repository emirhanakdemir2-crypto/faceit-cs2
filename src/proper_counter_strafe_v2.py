"""Proper Counter-Strafe V2 — engagement-gated rifle accuracy-of-stop metric.

Legacy first-bullet-moving metrics are untouched. V2 requires verified
engagement context and real demo max_speed; never fabricates ratios.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Callable

from src import suite_config as cfg
from src.duel_shot_context import UNAVAILABLE

MetricFilter = Callable[[dict[str, Any]], bool]


def _is_number(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return False


def _require_finite_non_negative(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def is_proper_speed_ratio(speed_ratio: Any) -> bool | None:
    """Proper iff speed_ratio <= V2_PROPER_SPEED_RATIO_MAX (inclusive)."""
    ratio = _require_finite_non_negative(speed_ratio)
    if ratio is None:
        return None
    return ratio <= cfg.V2_PROPER_SPEED_RATIO_MAX


def confidence_for_sample_size(eligible: int) -> str:
    if not isinstance(eligible, int) or isinstance(eligible, bool) or eligible < 0:
        return "none"
    if eligible >= cfg.V2_CONFIDENCE_HIGH_MIN_ELIGIBLE:
        return "high"
    if eligible >= cfg.V2_CONFIDENCE_MEDIUM_MIN_ELIGIBLE:
        return "medium"
    if eligible >= cfg.V2_CONFIDENCE_LOW_MIN_ELIGIBLE:
        return "low"
    return "none"


def _empty_v2(*, reason: str, experimental: bool = False) -> dict[str, Any]:
    return {
        "metric_label": cfg.V2_METRIC_LABEL,
        "legacy_metric_label": cfg.V2_LEGACY_METRIC_LABEL,
        "status": cfg.V2_STATUS_EXPERIMENTAL if experimental else cfg.V2_STATUS_UNAVAILABLE,
        "eligible_shots": 0,
        "proper_shots": 0,
        "improper_shots": 0,
        "proper_counter_strafe_pct": UNAVAILABLE,
        "first_bullet_eligible_shots": 0,
        "first_bullet_proper_pct": UNAVAILABLE,
        "median_speed_ratio": UNAVAILABLE,
        "p75_speed_ratio": UNAVAILABLE,
        "sample_size": 0,
        "confidence": "none",
        "eligibility_source": UNAVAILABLE,
        "unavailable_reason": reason,
        "experimental": experimental,
        "by_weapon": {},
    }


def _shot_eligible(ctx: dict[str, Any]) -> tuple[bool, str]:
    if not ctx.get("is_rifle"):
        return False, "non-rifle"
    crouch = ctx.get("crouch")
    if crouch is True:
        return False, "crouch"
    if crouch is UNAVAILABLE or crouch is None:
        return False, "crouch unavailable"
    if not ctx.get("engagement_verified"):
        return False, "engagement context unverified"
    if not _is_number(ctx.get("max_speed")):
        return False, "max_speed unavailable"
    if not _is_number(ctx.get("speed_ratio")):
        return False, "speed_ratio unavailable"
    src = ctx.get("eligibility_source")
    if src in (None, UNAVAILABLE, ""):
        return False, "eligibility_source unavailable"
    return True, ""


def _pct(proper: int, eligible: int) -> float | str:
    if eligible <= 0:
        return UNAVAILABLE
    return round(100.0 * proper / eligible, 1)


def _percentile(values: list[float], p: float) -> float | str:
    if not values:
        return UNAVAILABLE
    if len(values) == 1:
        return round(values[0], 4)
    qs = statistics.quantiles(values, n=100, method="inclusive")
    idx = max(0, min(len(qs) - 1, int(p) - 1))
    return round(qs[idx], 4)


def _aggregate_eligible(eligible_rows: list[dict[str, Any]], *, experimental: bool) -> dict[str, Any]:
    if not eligible_rows:
        return _empty_v2(
            reason="no eligible V2 rifle shots",
            experimental=experimental,
        )

    proper = 0
    ratios: list[float] = []
    first_eligible = 0
    first_proper = 0
    sources: set[str] = set()

    for row in eligible_rows:
        ratio = float(row["speed_ratio"])
        ratios.append(ratio)
        is_proper = is_proper_speed_ratio(ratio)
        if is_proper is True:
            proper += 1
        if row.get("is_first_bullet") is True:
            first_eligible += 1
            if is_proper is True:
                first_proper += 1
        src = row.get("eligibility_source")
        if isinstance(src, str):
            sources.add(src)

    eligible_n = len(eligible_rows)
    only_approx = sources == {cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED}
    status = cfg.V2_STATUS_EXPERIMENTAL if (experimental or only_approx) else "ok"

    return {
        "metric_label": cfg.V2_METRIC_LABEL,
        "legacy_metric_label": cfg.V2_LEGACY_METRIC_LABEL,
        "status": status,
        "eligible_shots": eligible_n,
        "proper_shots": proper,
        "improper_shots": eligible_n - proper,
        "proper_counter_strafe_pct": _pct(proper, eligible_n),
        "first_bullet_eligible_shots": first_eligible,
        "first_bullet_proper_pct": _pct(first_proper, first_eligible),
        "median_speed_ratio": (
            round(statistics.median(ratios), 4) if ratios else UNAVAILABLE
        ),
        "p75_speed_ratio": _percentile(ratios, 75),
        "sample_size": eligible_n,
        "confidence": confidence_for_sample_size(eligible_n),
        "eligibility_source": (
            cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED
            if only_approx
            else (",".join(sorted(sources)) if sources else UNAVAILABLE)
        ),
        "unavailable_reason": UNAVAILABLE if eligible_n else "no eligible V2 rifle shots",
        "experimental": status == cfg.V2_STATUS_EXPERIMENTAL,
        "by_weapon": {},
    }


def compute_proper_counter_strafe_v2(
    contexts: list[dict[str, Any]],
    *,
    weapon_filter: MetricFilter | None = None,
) -> dict[str, Any]:
    """Compute V2 metrics from duel shot contexts."""
    if not contexts:
        return _empty_v2(reason="no shot contexts")

    eligible_rows: list[dict[str, Any]] = []
    skip_reasons: dict[str, int] = {}
    saw_approx = False
    saw_hurt = False

    for ctx in contexts:
        if weapon_filter is not None and not weapon_filter(ctx):
            skip_reasons["weapon_filter"] = skip_reasons.get("weapon_filter", 0) + 1
            continue
        ok, reason = _shot_eligible(ctx)
        if not ok:
            skip_reasons[reason or "ineligible"] = skip_reasons.get(reason or "ineligible", 0) + 1
            continue
        src = ctx.get("eligibility_source")
        if src == cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED:
            saw_approx = True
        if src == cfg.V2_ELIGIBILITY_SOURCE_HURT:
            saw_hurt = True
        eligible_rows.append(ctx)

    experimental = saw_approx and not saw_hurt
    result = _aggregate_eligible(eligible_rows, experimental=experimental)
    if not eligible_rows and skip_reasons:
        # Prefer engagement/max_speed reasons for unavailable_reason
        preferred = (
            "engagement context unverified",
            "max_speed unavailable",
            "speed_ratio unavailable",
            "crouch",
            "non-rifle",
        )
        reason = next((p for p in preferred if p in skip_reasons), None)
        if reason is None:
            reason = max(skip_reasons.items(), key=lambda kv: kv[1])[0]
        result["unavailable_reason"] = reason
        result["skip_reasons"] = skip_reasons
    else:
        result["skip_reasons"] = skip_reasons
    return result


def compute_v2_weapon_breakdown(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    rifle = compute_proper_counter_strafe_v2(contexts, weapon_filter=lambda c: bool(c.get("is_rifle")))
    ak = compute_proper_counter_strafe_v2(contexts, weapon_filter=lambda c: bool(c.get("is_ak")))
    m4 = compute_proper_counter_strafe_v2(contexts, weapon_filter=lambda c: bool(c.get("is_m4")))
    rifle["by_weapon"] = {
        "ak": {k: ak[k] for k in (
            "eligible_shots", "proper_counter_strafe_pct", "first_bullet_proper_pct",
            "sample_size", "confidence", "status", "experimental", "unavailable_reason",
            "eligibility_source", "median_speed_ratio", "p75_speed_ratio",
            "first_bullet_eligible_shots", "proper_shots", "improper_shots",
        )},
        "m4": {k: m4[k] for k in (
            "eligible_shots", "proper_counter_strafe_pct", "first_bullet_proper_pct",
            "sample_size", "confidence", "status", "experimental", "unavailable_reason",
            "eligibility_source", "median_speed_ratio", "p75_speed_ratio",
            "first_bullet_eligible_shots", "proper_shots", "improper_shots",
        )},
    }
    return rifle
