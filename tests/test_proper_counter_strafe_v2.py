from __future__ import annotations

import unittest
from unittest.mock import patch

from src import proper_counter_strafe_v2 as v2
from src import suite_config as cfg
from src.duel_shot_context import UNAVAILABLE


def _ctx(**overrides):
    base = {
        "is_rifle": True,
        "is_ak": True,
        "is_m4": False,
        "crouch": False,
        "engagement_verified": True,
        "max_speed": 215.0,
        "velocity": 0.0,
        "speed_ratio": 0.0,
        "is_first_bullet": True,
        "eligibility_source": cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED,
        "weapon": "ak47",
    }
    base.update(overrides)
    return base


class ProperCounterStrafeV2Tests(unittest.TestCase):
    def test_non_rifle_excluded(self) -> None:
        result = v2.compute_proper_counter_strafe_v2([_ctx(is_rifle=False, is_ak=False)])
        self.assertEqual(result["eligible_shots"], 0)
        self.assertEqual(result["proper_counter_strafe_pct"], UNAVAILABLE)

    def test_crouch_excluded(self) -> None:
        result = v2.compute_proper_counter_strafe_v2([_ctx(crouch=True)])
        self.assertEqual(result["eligible_shots"], 0)
        self.assertEqual(result["unavailable_reason"], "crouch")

    def test_no_engagement_unavailable(self) -> None:
        result = v2.compute_proper_counter_strafe_v2([_ctx(engagement_verified=False)])
        self.assertEqual(result["proper_counter_strafe_pct"], UNAVAILABLE)
        self.assertEqual(result["unavailable_reason"], "engagement context unverified")

    def test_missing_max_speed_not_fabricated(self) -> None:
        result = v2.compute_proper_counter_strafe_v2([
            _ctx(max_speed=UNAVAILABLE, speed_ratio=UNAVAILABLE),
        ])
        self.assertEqual(result["eligible_shots"], 0)
        self.assertEqual(result["unavailable_reason"], "max_speed unavailable")

    def test_rejects_nan_inf_bool_negative_ratio(self) -> None:
        self.assertIsNone(v2.is_proper_speed_ratio(float("nan")))
        self.assertIsNone(v2.is_proper_speed_ratio(float("inf")))
        self.assertIsNone(v2.is_proper_speed_ratio(True))
        self.assertIsNone(v2.is_proper_speed_ratio(-0.1))

    def test_boundary_0_34_is_proper(self) -> None:
        self.assertTrue(v2.is_proper_speed_ratio(0.34))
        self.assertTrue(v2.is_proper_speed_ratio(cfg.V2_PROPER_SPEED_RATIO_MAX))

    def test_boundary_0_34001_is_improper(self) -> None:
        self.assertFalse(v2.is_proper_speed_ratio(0.34001))

    def test_ak_m4_split(self) -> None:
        contexts = [
            _ctx(is_ak=True, is_m4=False, speed_ratio=0.1, is_first_bullet=True),
            _ctx(is_ak=False, is_m4=True, is_rifle=True, speed_ratio=0.5, is_first_bullet=True, weapon="m4a1"),
        ]
        breakdown = v2.compute_v2_weapon_breakdown(contexts)
        self.assertEqual(breakdown["by_weapon"]["ak"]["eligible_shots"], 1)
        self.assertEqual(breakdown["by_weapon"]["m4"]["eligible_shots"], 1)
        self.assertEqual(breakdown["by_weapon"]["ak"]["proper_counter_strafe_pct"], 100.0)
        self.assertEqual(breakdown["by_weapon"]["m4"]["proper_counter_strafe_pct"], 0.0)

    def test_first_bullet_split(self) -> None:
        contexts = [
            _ctx(speed_ratio=0.1, is_first_bullet=True),
            _ctx(speed_ratio=0.9, is_first_bullet=False),
        ]
        result = v2.compute_proper_counter_strafe_v2(contexts)
        self.assertEqual(result["eligible_shots"], 2)
        self.assertEqual(result["first_bullet_eligible_shots"], 1)
        self.assertEqual(result["first_bullet_proper_pct"], 100.0)
        self.assertEqual(result["proper_counter_strafe_pct"], 50.0)

    def test_empty_sample_does_not_invent_pct(self) -> None:
        result = v2.compute_proper_counter_strafe_v2([])
        self.assertEqual(result["proper_counter_strafe_pct"], UNAVAILABLE)
        self.assertEqual(result["first_bullet_proper_pct"], UNAVAILABLE)
        self.assertEqual(result["sample_size"], 0)

    def test_confidence_scales_with_sample_size(self) -> None:
        self.assertEqual(v2.confidence_for_sample_size(0), "none")
        self.assertEqual(v2.confidence_for_sample_size(cfg.V2_CONFIDENCE_LOW_MIN_ELIGIBLE), "low")
        self.assertEqual(v2.confidence_for_sample_size(cfg.V2_CONFIDENCE_MEDIUM_MIN_ELIGIBLE), "medium")
        self.assertEqual(v2.confidence_for_sample_size(cfg.V2_CONFIDENCE_HIGH_MIN_ELIGIBLE), "high")

    def test_approx_only_marked_experimental(self) -> None:
        result = v2.compute_proper_counter_strafe_v2([
            _ctx(eligibility_source=cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED, speed_ratio=0.2),
        ])
        self.assertTrue(result["experimental"])
        self.assertEqual(result["status"], cfg.V2_STATUS_EXPERIMENTAL)

    def test_legacy_fields_untouched_by_v2_module(self) -> None:
        result = v2.compute_proper_counter_strafe_v2([_ctx(speed_ratio=0.2)])
        self.assertEqual(result["metric_label"], cfg.V2_METRIC_LABEL)
        self.assertEqual(result["legacy_metric_label"], cfg.V2_LEGACY_METRIC_LABEL)
        self.assertNotEqual(result["metric_label"], "rifle_first_bullet_moving_pct")
        self.assertNotIn("rifle_first_bullet_moving_pct", result)

    def test_does_not_touch_real_db_or_network(self) -> None:
        with patch("src.storage._connect", side_effect=AssertionError("DB")):
            with patch("requests.Session.get", side_effect=AssertionError("NET")):
                result = v2.compute_proper_counter_strafe_v2([_ctx(speed_ratio=0.2)])
        self.assertEqual(result["eligible_shots"], 1)


if __name__ == "__main__":
    unittest.main()
