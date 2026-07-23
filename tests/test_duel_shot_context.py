from __future__ import annotations

import unittest

from src import duel_shot_context as dsc
from src import suite_config as cfg


class DuelShotContextTests(unittest.TestCase):
    def _tick(
        self,
        *,
        tick: int,
        steamid: str,
        team: int,
        velocity: float = 0.0,
        max_speed: float = 215.0,
        ducked: bool = False,
        ducking: bool = False,
        spotted_by: list | None = None,
        name: str = "P",
        entity_id: int = 1,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        pitch: float = 0.0,
        yaw: float = 0.0,
        total_rounds_played: int = 3,
    ) -> dict:
        return {
            "tick": tick,
            "steamid": steamid,
            "name": name,
            "team_num": team,
            "velocity": velocity,
            "max_speed": max_speed,
            "ducked": ducked,
            "ducking": ducking,
            "approximate_spotted_by": spotted_by or [],
            "entity_id": entity_id,
            "X": x,
            "Y": y,
            "Z": z,
            "pitch": pitch,
            "yaw": yaw,
            "total_rounds_played": total_rounds_played,
        }

    def test_resolves_approximate_spotted_by_steamid_list(self) -> None:
        shooter = self._tick(
            tick=100,
            steamid="111",
            team=2,
            spotted_by=["222"],
            entity_id=10,
        )
        enemy = self._tick(
            tick=100,
            steamid="222",
            team=3,
            spotted_by=[],
            entity_id=20,
            name="Enemy",
        )
        teammate = self._tick(
            tick=100,
            steamid="333",
            team=2,
            spotted_by=["111"],
            entity_id=30,
            name="Mate",
        )
        enemies = dsc.resolve_approximate_spotted_enemies(
            shooter, [shooter, enemy, teammate], "111",
        )
        self.assertEqual(len(enemies), 1)
        self.assertEqual(enemies[0]["steamid"], "222")
        self.assertEqual(
            enemies[0]["eligibility_source"],
            cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED,
        )

    def test_mutual_spotted_mask_resolution(self) -> None:
        shooter = self._tick(tick=50, steamid="111", team=2, spotted_by=[])
        enemy = self._tick(tick=50, steamid="222", team=3, spotted_by=["111"])
        enemies = dsc.resolve_approximate_spotted_enemies(
            shooter, [shooter, enemy], "111",
        )
        self.assertEqual(len(enemies), 1)
        self.assertEqual(enemies[0]["steamid"], "222")

    def test_does_not_invent_target_for_miss_without_engagement(self) -> None:
        ticks = [
            self._tick(tick=10, steamid="111", team=2, spotted_by=[]),
            self._tick(tick=10, steamid="222", team=3, spotted_by=[]),
        ]
        shots = [{"tick": 10, "weapon": "ak47", "user_steamid": "111"}]
        # Hurt exists but for a different tick — must not back-assign to this miss.
        hurts = [{
            "tick": 999,
            "attacker_steamid": "111",
            "user_steamid": "222",
            "user_name": "Enemy",
        }]
        ctxs = dsc.build_shot_contexts(
            demo_id="demoA",
            shooter_steamid="111",
            shot_rows=shots,
            tick_rows=ticks,
            hurt_rows=hurts,
        )
        self.assertEqual(len(ctxs), 1)
        self.assertFalse(ctxs[0]["engagement_verified"])
        self.assertEqual(ctxs[0]["target_steamid"], dsc.UNAVAILABLE)
        self.assertEqual(ctxs[0]["eligibility_source"], dsc.UNAVAILABLE)

    def test_hurt_confirms_target_only_near_shot_tick(self) -> None:
        ticks = [
            self._tick(tick=100, steamid="111", team=2, spotted_by=[]),
            self._tick(tick=100, steamid="222", team=3, spotted_by=[]),
        ]
        shots = [{"tick": 100, "weapon": "ak47"}]
        hurts = [{
            "tick": 101,
            "attacker_steamid": "111",
            "user_steamid": "222",
            "user_name": "Enemy",
        }]
        ctxs = dsc.build_shot_contexts(
            demo_id="demoA",
            shooter_steamid="111",
            shot_rows=shots,
            tick_rows=ticks,
            hurt_rows=hurts,
        )
        self.assertTrue(ctxs[0]["engagement_verified"])
        self.assertEqual(ctxs[0]["target_steamid"], "222")
        self.assertEqual(
            ctxs[0]["eligibility_source"],
            cfg.V2_ELIGIBILITY_SOURCE_HURT,
        )

    def test_max_speed_missing_not_fabricated(self) -> None:
        ticks = [
            self._tick(tick=1, steamid="111", team=2, max_speed=None, spotted_by=["222"]),  # type: ignore[arg-type]
            self._tick(tick=1, steamid="222", team=3, spotted_by=["111"]),
        ]
        ticks[0].pop("max_speed")
        shots = [{"tick": 1, "weapon": "ak47"}]
        ctxs = dsc.build_shot_contexts(
            demo_id="demoA",
            shooter_steamid="111",
            shot_rows=shots,
            tick_rows=ticks,
        )
        self.assertEqual(ctxs[0]["max_speed"], dsc.UNAVAILABLE)
        self.assertEqual(ctxs[0]["speed_ratio"], dsc.UNAVAILABLE)
        self.assertIn("max_speed", str(ctxs[0]["unavailable_reason"]))

    def test_rejects_non_finite_velocity_for_ratio(self) -> None:
        self.assertIsNone(dsc._speed_ratio(float("nan"), 215.0))
        self.assertIsNone(dsc._speed_ratio(float("inf"), 215.0))
        self.assertIsNone(dsc._speed_ratio(10.0, float("nan")))
        self.assertIsNone(dsc._speed_ratio(True, 215.0))  # type: ignore[arg-type]
        self.assertIsNone(dsc._speed_ratio(-1.0, 215.0))

    def test_first_bullet_burst_index(self) -> None:
        ticks = [
            self._tick(tick=10, steamid="111", team=2, spotted_by=["222"]),
            self._tick(tick=10, steamid="222", team=3, spotted_by=["111"]),
            self._tick(tick=12, steamid="111", team=2, spotted_by=["222"]),
            self._tick(tick=12, steamid="222", team=3, spotted_by=["111"]),
            self._tick(tick=100, steamid="111", team=2, spotted_by=["222"]),
            self._tick(tick=100, steamid="222", team=3, spotted_by=["111"]),
        ]
        shots = [
            {"tick": 10, "weapon": "ak47"},
            {"tick": 12, "weapon": "ak47"},
            {"tick": 100, "weapon": "ak47"},
        ]
        ctxs = dsc.build_shot_contexts(
            demo_id="demoA",
            shooter_steamid="111",
            shot_rows=shots,
            tick_rows=ticks,
        )
        self.assertTrue(ctxs[0]["is_first_bullet"])
        self.assertEqual(ctxs[0]["shot_index_in_burst"], 1)
        self.assertFalse(ctxs[1]["is_first_bullet"])
        self.assertEqual(ctxs[1]["shot_index_in_burst"], 2)
        self.assertTrue(ctxs[2]["is_first_bullet"])

    def test_context_marks_rifle_ak_m4(self) -> None:
        ticks = [
            self._tick(tick=1, steamid="111", team=2, spotted_by=["222"]),
            self._tick(tick=1, steamid="222", team=3, spotted_by=["111"]),
        ]
        for weapon, is_ak, is_m4 in (("ak47", True, False), ("m4a1", False, True), ("glock", False, False)):
            ctxs = dsc.build_shot_contexts(
                demo_id="d",
                shooter_steamid="111",
                shot_rows=[{"tick": 1, "weapon": weapon}],
                tick_rows=ticks,
            )
            self.assertEqual(ctxs[0]["is_ak"], is_ak)
            self.assertEqual(ctxs[0]["is_m4"], is_m4)
            self.assertEqual(ctxs[0]["is_rifle"], weapon != "glock")


if __name__ == "__main__":
    unittest.main()
