"""Proper Counter-Strafe V2 — engagement-gated rifle accuracy-of-stop metric.

Headline pool uses only approximate-spotted evidence (spotted_only and
spotted_and_hurt). hurt_only is diagnostic and never enters the headline
numerator/denominator. Measurement quality stays experimental while the
source is approximate_spotted_mask (not true LoS).
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Callable

from src import suite_config as cfg
from src.duel_shot_context import UNAVAILABLE

MetricFilter = Callable[[dict[str, Any]], bool]

HEADLINE_BUCKETS = set(cfg.V2_HEADLINE_EVIDENCE_BUCKETS)
DIAGNOSTIC_BUCKETS = (
    cfg.V2_EVIDENCE_SPOTTED_ONLY,
    cfg.V2_EVIDENCE_SPOTTED_AND_HURT,
    cfg.V2_EVIDENCE_HURT_ONLY,
    cfg.V2_EVIDENCE_UNRESOLVED,
)


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


def sample_confidence_for_size(eligible: int) -> str:
    if not isinstance(eligible, int) or isinstance(eligible, bool) or eligible < 0:
        return "none"
    if eligible >= cfg.V2_CONFIDENCE_HIGH_MIN_ELIGIBLE:
        return "high"
    if eligible >= cfg.V2_CONFIDENCE_MEDIUM_MIN_ELIGIBLE:
        return "medium"
    if eligible >= cfg.V2_CONFIDENCE_LOW_MIN_ELIGIBLE:
        return "low"
    return "none"


# Backward-compatible alias used by older callers/tests.
confidence_for_sample_size = sample_confidence_for_size


def _pct(proper: int, eligible: int) -> float | str:
    if eligible <= 0:
        return UNAVAILABLE
    return round(100.0 * proper / eligible, 1)


def _coverage_pct(eligible: int, base: int) -> float | str:
    if base <= 0:
        return UNAVAILABLE
    return round(100.0 * eligible / base, 1)


def _percentile(values: list[float], p: float) -> float | str:
    if not values:
        return UNAVAILABLE
    if len(values) == 1:
        return round(values[0], 4)
    qs = statistics.quantiles(values, n=100, method="inclusive")
    idx = max(0, min(len(qs) - 1, int(p) - 1))
    return round(qs[idx], 4)


def _bucket_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    proper = 0
    first_el = 0
    first_pr = 0
    ratios: list[float] = []
    for row in rows:
        ratio = float(row["speed_ratio"])
        ratios.append(ratio)
        ok = is_proper_speed_ratio(ratio) is True
        if ok:
            proper += 1
        if row.get("is_first_bullet") is True:
            first_el += 1
            if ok:
                first_pr += 1
    n = len(rows)
    return {
        "n": n,
        "proper_shots": proper,
        "improper_shots": n - proper,
        "proper_counter_strafe_pct": _pct(proper, n),
        "first_bullet_eligible_shots": first_el,
        "first_bullet_proper_pct": _pct(first_pr, first_el),
        "median_speed_ratio": round(statistics.median(ratios), 4) if ratios else UNAVAILABLE,
        "p75_speed_ratio": _percentile(ratios, 75),
    }


def _is_base_candidate(ctx: dict[str, Any]) -> bool:
    """Non-crouched rifle shot candidate (coverage denominator)."""
    if not ctx.get("is_rifle"):
        return False
    crouch = ctx.get("crouch")
    if crouch is True:
        return False
    if crouch is UNAVAILABLE or crouch is None:
        return False
    return True


def _passes_metric_prereqs(ctx: dict[str, Any]) -> tuple[bool, str]:
    if not _is_base_candidate(ctx):
        if not ctx.get("is_rifle"):
            return False, "non-rifle"
        if ctx.get("crouch") is True:
            return False, "crouch"
        return False, "crouch unavailable"
    if not _is_number(ctx.get("max_speed")):
        return False, "max_speed unavailable"
    if not _is_number(ctx.get("speed_ratio")):
        return False, "speed_ratio unavailable"
    return True, ""


def _empty_v2(*, reason: str) -> dict[str, Any]:
    empty_bucket = {
        "n": 0,
        "proper_shots": 0,
        "improper_shots": 0,
        "proper_counter_strafe_pct": UNAVAILABLE,
        "first_bullet_eligible_shots": 0,
        "first_bullet_proper_pct": UNAVAILABLE,
        "median_speed_ratio": UNAVAILABLE,
        "p75_speed_ratio": UNAVAILABLE,
    }
    return {
        "metric_label": cfg.V2_METRIC_LABEL,
        "display_title": cfg.V2_DISPLAY_TITLE,
        "legacy_metric_label": cfg.V2_LEGACY_METRIC_LABEL,
        "status": cfg.V2_STATUS_UNAVAILABLE,
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
        "sample_confidence": "none",
        "measurement_quality": cfg.V2_MEASUREMENT_QUALITY_EXPERIMENTAL,
        "eligibility_source": cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED,
        "unavailable_reason": reason,
        "experimental": True,
        "coach_soft_label": cfg.V2_COACH_SOFT_LABEL,
        "base_rifle_non_crouch_candidates": 0,
        "spotted_eligible_shots": 0,
        "eligibility_coverage_pct": UNAVAILABLE,
        "first_bullet_base_candidates": 0,
        "first_bullet_spotted_eligible_shots": 0,
        "first_bullet_eligibility_coverage_pct": UNAVAILABLE,
        "source_counts": {b: dict(empty_bucket) for b in DIAGNOSTIC_BUCKETS},
        "by_weapon": {},
    }


def compute_proper_counter_strafe_v2(
    contexts: list[dict[str, Any]],
    *,
    weapon_filter: MetricFilter | None = None,
) -> dict[str, Any]:
    """Compute V2 metrics; headline excludes hurt_only shots."""
    if not contexts:
        return _empty_v2(reason="no shot contexts")

    filtered = [
        ctx for ctx in contexts
        if weapon_filter is None or weapon_filter(ctx)
    ]
    if not filtered:
        return _empty_v2(reason="no shot contexts after weapon filter")

    base_candidates: list[dict[str, Any]] = []
    headline_rows: list[dict[str, Any]] = []
    bucket_rows: dict[str, list[dict[str, Any]]] = {b: [] for b in DIAGNOSTIC_BUCKETS}
    skip_reasons: dict[str, int] = {}

    for ctx in filtered:
        bucket = ctx.get("evidence_bucket") or cfg.V2_EVIDENCE_UNRESOLVED
        if bucket not in bucket_rows:
            bucket = cfg.V2_EVIDENCE_UNRESOLVED

        if not _is_base_candidate(ctx):
            reason = "non-rifle" if not ctx.get("is_rifle") else (
                "crouch" if ctx.get("crouch") is True else "crouch unavailable"
            )
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            continue

        base_candidates.append(ctx)
        ok, reason = _passes_metric_prereqs(ctx)
        if not ok:
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            # Still count unresolved/hurt diagnostic only when prereqs fail? No —
            # diagnostic proper% needs speed_ratio; skip incomplete.
            continue

        bucket_rows[bucket].append(ctx)
        if bucket in HEADLINE_BUCKETS:
            headline_rows.append(ctx)

    source_counts = {b: _bucket_stats(rows) for b, rows in bucket_rows.items()}
    result = _empty_v2(reason="no spotted-eligible V2 rifle shots")
    result["skip_reasons"] = skip_reasons
    result["source_counts"] = source_counts
    result["base_rifle_non_crouch_candidates"] = len(base_candidates)
    result["first_bullet_base_candidates"] = sum(
        1 for c in base_candidates if c.get("is_first_bullet") is True
    )

    if not headline_rows:
        preferred = (
            "max_speed unavailable",
            "speed_ratio unavailable",
            "crouch",
            "crouch unavailable",
            "non-rifle",
            "engagement context unverified",
            "no spotted-eligible V2 rifle shots",
        )
        if skip_reasons:
            reason = next((p for p in preferred if p in skip_reasons), None)
            if reason is None:
                reason = max(skip_reasons.items(), key=lambda kv: kv[1])[0]
            result["unavailable_reason"] = reason
        else:
            result["unavailable_reason"] = "no spotted-eligible V2 rifle shots"
        result["spotted_eligible_shots"] = 0
        result["eligibility_coverage_pct"] = _coverage_pct(0, len(base_candidates))
        result["first_bullet_spotted_eligible_shots"] = 0
        result["first_bullet_eligibility_coverage_pct"] = _coverage_pct(
            0, result["first_bullet_base_candidates"],
        )
        result["measurement_quality"] = cfg.V2_MEASUREMENT_QUALITY_EXPERIMENTAL
        result["eligibility_source"] = cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED
        result["experimental"] = True
        return result

    stats = _bucket_stats(headline_rows)
    eligible_n = stats["n"]
    first_el = stats["first_bullet_eligible_shots"]
    result.update({
        "status": cfg.V2_STATUS_EXPERIMENTAL,
        "eligible_shots": eligible_n,
        "proper_shots": stats["proper_shots"],
        "improper_shots": stats["improper_shots"],
        "proper_counter_strafe_pct": stats["proper_counter_strafe_pct"],
        "first_bullet_eligible_shots": first_el,
        "first_bullet_proper_pct": stats["first_bullet_proper_pct"],
        "median_speed_ratio": stats["median_speed_ratio"],
        "p75_speed_ratio": stats["p75_speed_ratio"],
        "sample_size": eligible_n,
        "sample_confidence": sample_confidence_for_size(eligible_n),
        "confidence": sample_confidence_for_size(eligible_n),
        "measurement_quality": cfg.V2_MEASUREMENT_QUALITY_EXPERIMENTAL,
        "eligibility_source": cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED,
        "unavailable_reason": UNAVAILABLE,
        "experimental": True,
        "spotted_eligible_shots": eligible_n,
        "eligibility_coverage_pct": _coverage_pct(eligible_n, len(base_candidates)),
        "first_bullet_spotted_eligible_shots": first_el,
        "first_bullet_eligibility_coverage_pct": _coverage_pct(
            first_el, result["first_bullet_base_candidates"],
        ),
        "coach_soft_label": cfg.V2_COACH_SOFT_LABEL,
        "display_title": cfg.V2_DISPLAY_TITLE,
    })
    return result


def compute_v2_weapon_breakdown(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    rifle = compute_proper_counter_strafe_v2(
        contexts, weapon_filter=lambda c: bool(c.get("is_rifle")),
    )
    ak = compute_proper_counter_strafe_v2(
        contexts, weapon_filter=lambda c: bool(c.get("is_ak")),
    )
    m4 = compute_proper_counter_strafe_v2(
        contexts, weapon_filter=lambda c: bool(c.get("is_m4")),
    )
    keys = (
        "eligible_shots", "proper_counter_strafe_pct", "first_bullet_proper_pct",
        "sample_size", "sample_confidence", "confidence", "status", "experimental",
        "measurement_quality", "unavailable_reason", "eligibility_source",
        "median_speed_ratio", "p75_speed_ratio", "first_bullet_eligible_shots",
        "proper_shots", "improper_shots", "source_counts",
        "eligibility_coverage_pct", "base_rifle_non_crouch_candidates",
        "spotted_eligible_shots", "first_bullet_eligibility_coverage_pct",
        "display_title", "coach_soft_label",
    )
    rifle["by_weapon"] = {
        "ak": {k: ak.get(k) for k in keys},
        "m4": {k: m4.get(k) for k in keys},
    }
    return rifle
