from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import suite_config as cfg
from src import visibility_agreement as va
from src.geometry_visibility import FakeVisibilityChecker, GeometryVisibilityBackend, UNAVAILABLE


def _backend(visible=True, map_name: str = "de_dust2") -> GeometryVisibilityBackend:
    root = Path(tempfile.mkdtemp())
    (root / f"{map_name}.tri").write_bytes(b"tri")
    return GeometryVisibilityBackend(
        tris_dir=root,
        checker_factory=lambda _p: FakeVisibilityChecker(visible),
        backend_source="fake",
        backend_version="test",
    )


def _player(
    *,
    steamid: str,
    team: int,
    x: float,
    y: float,
    z: float = 0.0,
    pitch: float = 0.0,
    yaw: float = 0.0,
    alive: bool = True,
    health: float = 100.0,
    spotted_by: list | None = None,
    ducked: bool = False,
    fov: float = 0.0,
) -> dict:
    return {
        "steamid": steamid,
        "team_num": team,
        "X": x,
        "Y": y,
        "Z": z,
        "pitch": pitch,
        "yaw": yaw,
        "is_alive": alive,
        "health": health,
        "life_state": 0 if alive else 1,
        "approximate_spotted_by": spotted_by or [],
        "ducked": ducked,
        "ducking": False,
        "fov": fov,
    }


class VisibilityAgreementTests(unittest.TestCase):
    def test_teammate_not_counted_as_enemy(self) -> None:
        backend = _backend(True)
        shooter = _player(steamid="1", team=2, x=0, y=0, yaw=0)
        mate = _player(steamid="2", team=2, x=200, y=0)
        out = va.evaluate_shot_visibility(
            map_name="de_dust2",
            shooter_row=shooter,
            frame_rows=[shooter, mate],
            backend=backend,
        )
        self.assertEqual(out["visible_enemy_count"], 0)
        self.assertFalse(out["approx_enemy_in_view"])

    def test_dead_player_not_counted(self) -> None:
        backend = _backend(True)
        shooter = _player(steamid="1", team=2, x=0, y=0, yaw=0)
        dead = _player(steamid="9", team=3, x=200, y=0, alive=False, health=0)
        out = va.evaluate_shot_visibility(
            map_name="de_dust2",
            shooter_row=shooter,
            frame_rows=[shooter, dead],
            backend=backend,
        )
        self.assertEqual(out["visible_enemy_count"], 0)

    def test_enemy_outside_fov_not_visible(self) -> None:
        backend = _backend(True)
        # Shooter looks +X (yaw=0). Enemy is on +Y axis → ~90° off.
        shooter = _player(steamid="1", team=2, x=0, y=0, yaw=0, pitch=0)
        enemy = _player(steamid="9", team=3, x=0, y=200)
        out = va.evaluate_shot_visibility(
            map_name="de_dust2",
            shooter_row=shooter,
            frame_rows=[shooter, enemy],
            backend=backend,
        )
        self.assertTrue(out["geometry_any_clear"])
        self.assertEqual(out["visible_enemy_count"], 0)
        self.assertFalse(out["approx_enemy_in_view"])

    def test_multiple_enemies_do_not_invent_target(self) -> None:
        backend = _backend(True)
        shooter = _player(steamid="1", team=2, x=0, y=0, yaw=0)
        e1 = _player(steamid="8", team=3, x=150, y=0)
        e2 = _player(steamid="9", team=3, x=180, y=5)
        out = va.evaluate_shot_visibility(
            map_name="de_dust2",
            shooter_row=shooter,
            frame_rows=[shooter, e1, e2],
            backend=backend,
        )
        self.assertEqual(out["visible_enemy_count"], 2)
        self.assertEqual(out["target_steamid"], UNAVAILABLE)

    def test_unique_enemy_sets_target(self) -> None:
        backend = _backend(True)
        shooter = _player(steamid="1", team=2, x=0, y=0, yaw=0)
        enemy = _player(steamid="9", team=3, x=150, y=0)
        out = va.evaluate_shot_visibility(
            map_name="de_dust2",
            shooter_row=shooter,
            frame_rows=[shooter, enemy],
            backend=backend,
        )
        self.assertEqual(out["visible_enemy_count"], 1)
        self.assertEqual(out["target_steamid"], "9")

    def test_four_agreement_buckets(self) -> None:
        cases = [
            (True, ["9"], cfg.GEOMETRY_AGREEMENT_VISIBLE_SPOTTED),
            (True, [], cfg.GEOMETRY_AGREEMENT_VISIBLE_NOT_SPOTTED),
            (False, ["9"], cfg.GEOMETRY_AGREEMENT_BLOCKED_SPOTTED),
            (False, [], cfg.GEOMETRY_AGREEMENT_BLOCKED_NOT_SPOTTED),
        ]
        for visible, spotted, expected in cases:
            backend = _backend(visible)
            shooter = _player(
                steamid="1", team=2, x=0, y=0, yaw=0, spotted_by=spotted,
            )
            enemy = _player(steamid="9", team=3, x=150, y=0)
            out = va.evaluate_shot_visibility(
                map_name="de_dust2",
                shooter_row=shooter,
                frame_rows=[shooter, enemy],
                backend=backend,
            )
            self.assertEqual(out["agreement_bucket"], expected, msg=(visible, spotted))

    def test_missing_eye_xyz_no_definitive_visibility(self) -> None:
        backend = _backend(True)
        shooter = _player(steamid="1", team=2, x=0, y=0)
        shooter.pop("Z")
        enemy = _player(steamid="9", team=3, x=100, y=0)
        out = va.evaluate_shot_visibility(
            map_name="de_dust2",
            shooter_row=shooter,
            frame_rows=[shooter, enemy],
            backend=backend,
        )
        self.assertEqual(out["enemy_visible"], UNAVAILABLE)
        self.assertEqual(out.get("approx_enemy_in_view"), None)

    def test_require_definitive_eye_fov_blocks_hard_visibility(self) -> None:
        backend = _backend(True)
        shooter = _player(steamid="1", team=2, x=0, y=0, yaw=0, fov=0)
        enemy = _player(steamid="9", team=3, x=150, y=0)
        out = va.evaluate_shot_visibility(
            map_name="de_dust2",
            shooter_row=shooter,
            frame_rows=[shooter, enemy],
            backend=backend,
            require_definitive_eye_fov=True,
        )
        self.assertEqual(out["enemy_visible"], UNAVAILABLE)
        self.assertIn("definitive", str(out.get("unavailable_reason")))

    def test_measurement_quality_never_validated(self) -> None:
        backend = _backend(True)
        shooter = _player(steamid="1", team=2, x=0, y=0, yaw=0)
        enemy = _player(steamid="9", team=3, x=150, y=0)
        out = va.evaluate_shot_visibility(
            map_name="de_dust2",
            shooter_row=shooter,
            frame_rows=[shooter, enemy],
            backend=backend,
        )
        self.assertEqual(out["measurement_quality"], cfg.GEOMETRY_MEASUREMENT_QUALITY)
        self.assertNotEqual(out["measurement_quality"], "validated")
        empty = va.compute_visibility_agreement(
            map_name="de_dust2",
            shooter_steamid="1",
            shot_ticks=[],
            tick_rows=[],
            backend=backend,
        )
        self.assertNotEqual(empty["measurement_quality"], "validated")

    def test_blocked_geometry_enemy_not_in_view(self) -> None:
        backend = _backend(False)
        shooter = _player(steamid="1", team=2, x=0, y=0, yaw=0)
        enemy = _player(steamid="9", team=3, x=150, y=0)
        out = va.evaluate_shot_visibility(
            map_name="de_dust2",
            shooter_row=shooter,
            frame_rows=[shooter, enemy],
            backend=backend,
        )
        self.assertFalse(out["geometry_any_clear"])
        self.assertEqual(out["visible_enemy_count"], 0)

    def test_agreement_summary_counts(self) -> None:
        backend = _backend(True)
        shooter = _player(steamid="1", team=2, x=0, y=0, yaw=0, spotted_by=["9"])
        enemy = _player(steamid="9", team=3, x=150, y=0)
        tick_rows = []
        for tick in (10, 20):
            s = dict(shooter)
            e = dict(enemy)
            s["tick"] = tick
            e["tick"] = tick
            tick_rows.extend([s, e])
        summary = va.compute_visibility_agreement(
            map_name="de_dust2",
            shooter_steamid="1",
            shot_ticks=[10, 20],
            tick_rows=tick_rows,
            backend=backend,
        )
        self.assertEqual(summary["geometry_resolved_count"], 2)
        self.assertEqual(
            summary["buckets"][cfg.GEOMETRY_AGREEMENT_VISIBLE_SPOTTED], 2,
        )
        self.assertEqual(summary["agreement_pct"], 100.0)
        self.assertEqual(backend.create_counts.get("de_dust2"), 1)

    def test_does_not_touch_db_or_network(self) -> None:
        with patch("src.storage._connect", side_effect=AssertionError("DB")):
            with patch("requests.Session.get", side_effect=AssertionError("NET")):
                backend = _backend(True)
                shooter = _player(steamid="1", team=2, x=0, y=0, yaw=0)
                enemy = _player(steamid="9", team=3, x=120, y=0)
                out = va.evaluate_shot_visibility(
                    map_name="de_dust2",
                    shooter_row=shooter,
                    frame_rows=[shooter, enemy],
                    backend=backend,
                )
        self.assertEqual(out["visible_enemy_count"], 1)


if __name__ == "__main__":
    unittest.main()
