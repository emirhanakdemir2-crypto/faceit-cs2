from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import suite_config as cfg
from src.demo_parser import collect_shot_tick_window, extract_duel_tick_rows
from src.geometry_visibility import FakeVisibilityChecker, GeometryVisibilityBackend
from src import visibility_agreement as va
from src.proper_counter_strafe_v2 import compute_proper_counter_strafe_v2


class ShotWindowSamplingTests(unittest.TestCase):
    def test_collect_shot_tick_window_expands_tolerance(self) -> None:
        rows = [{"tick": 100}, {"tick": 100}, {"tick": 110}]
        got = collect_shot_tick_window(rows, tolerance=2)
        self.assertEqual(got, [98, 99, 100, 101, 102, 108, 109, 110, 111, 112])

    def test_empty_shot_list_skips_geometry_parse(self) -> None:
        parser = MagicMock()
        out = extract_duel_tick_rows(parser, ticks=[])
        parser.parse_ticks.assert_not_called()
        self.assertFalse(out["available"])
        self.assertEqual(out["sampling"], "shot_window_empty")
        self.assertEqual(out["rows"], [])

    def test_player_ticks_also_accept_shot_window(self) -> None:
        from src.demo_parser import extract_player_ticks_if_available
        import pandas as pd

        parser = MagicMock()
        parser.parse_ticks.return_value = pd.DataFrame(
            [{"tick": 10, "steamid": 1, "X": 0.0, "Y": 0.0, "Z": 0.0, "velocity": 1.0, "name": "A"}]
        )
        out = extract_player_ticks_if_available(
            parser, "A", matched_steamid=1, ticks=[10, 11],
        )
        kwargs = parser.parse_ticks.call_args.kwargs
        self.assertEqual(kwargs.get("ticks"), [10, 11])
        self.assertEqual(kwargs.get("players"), [1])
        self.assertEqual(out["sampling"], "shot_window")
        self.assertEqual(out["tick_count"], 1)
    def test_extract_duel_passes_only_requested_ticks(self) -> None:
        parser = MagicMock()
        import pandas as pd

        parser.parse_ticks.return_value = pd.DataFrame(
            [
                {"tick": 10, "steamid": "1", "X": 0.0, "Y": 0.0, "Z": 0.0},
                {"tick": 12, "steamid": "1", "X": 1.0, "Y": 0.0, "Z": 0.0},
            ]
        )
        out = extract_duel_tick_rows(parser, ticks=[10, 12])
        kwargs = parser.parse_ticks.call_args.kwargs
        self.assertEqual(kwargs.get("ticks"), [10, 12])
        self.assertEqual(out["sampling"], "shot_window")
        self.assertEqual(out["ticks_filter_count"], 2)
        self.assertEqual(len(out["rows"]), 2)

    def test_optimized_path_parity_with_full_rows(self) -> None:
        """Same frames ⇒ identical agreement buckets whether extra ticks exist."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "de_dust2.tri").write_bytes(b"tri")
            backend = GeometryVisibilityBackend(
                tris_dir=root,
                checker_factory=lambda _p: FakeVisibilityChecker(True),
            )

            def frame(tick: int) -> list[dict]:
                shooter = {
                    "tick": tick,
                    "steamid": "1",
                    "team_num": 2,
                    "X": 0.0,
                    "Y": 0.0,
                    "Z": 0.0,
                    "pitch": 0.0,
                    "yaw": 0.0,
                    "is_alive": True,
                    "health": 100,
                    "life_state": 0,
                    "approximate_spotted_by": ["9"],
                    "ducked": False,
                    "ducking": False,
                    "fov": 0,
                }
                enemy = {
                    "tick": tick,
                    "steamid": "9",
                    "team_num": 3,
                    "X": 150.0,
                    "Y": 0.0,
                    "Z": 0.0,
                    "pitch": 0.0,
                    "yaw": 180.0,
                    "is_alive": True,
                    "health": 100,
                    "life_state": 0,
                    "approximate_spotted_by": [],
                    "ducked": False,
                    "ducking": False,
                    "fov": 0,
                }
                return [shooter, enemy]

            shot_ticks = [100, 200, 300]
            needed = frame(100) + frame(200) + frame(300)
            extras = frame(999)  # would only exist on full-matrix path
            full = va.compute_visibility_agreement(
                map_name="de_dust2",
                shooter_steamid="1",
                shot_ticks=shot_ticks,
                tick_rows=needed + extras,
                backend=backend,
            )
            backend.clear_cache()
            sampled = va.compute_visibility_agreement(
                map_name="de_dust2",
                shooter_steamid="1",
                shot_ticks=shot_ticks,
                tick_rows=needed,
                backend=backend,
            )
        self.assertEqual(full["geometry_resolved_count"], sampled["geometry_resolved_count"])
        self.assertEqual(full["agreement_pct"], sampled["agreement_pct"])
        self.assertEqual(full["disagreement_pct"], sampled["disagreement_pct"])
        self.assertEqual(full["buckets"], sampled["buckets"])
        self.assertEqual(full["mean_visible_enemy_count"], sampled["mean_visible_enemy_count"])
        self.assertEqual(full["measurement_quality"], cfg.GEOMETRY_MEASUREMENT_QUALITY)
        self.assertNotEqual(full["measurement_quality"], "validated")

    def test_map_switch_does_not_reuse_wrong_checker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "de_dust2.tri").write_bytes(b"a")
            (root / "de_mirage.tri").write_bytes(b"b")
            created: list[str] = []

            def factory(path: Path):
                created.append(path.stem)
                return FakeVisibilityChecker(path.stem == "de_mirage")

            backend = GeometryVisibilityBackend(
                tris_dir=root, checker_factory=factory,
            )
            d2 = backend.is_visible("de_dust2", (0, 0, 0), (1, 0, 0))
            mir = backend.is_visible("de_mirage", (0, 0, 0), (1, 0, 0))
            again = backend.is_visible("de_mirage", (0, 0, 0), (2, 0, 0))
        self.assertFalse(d2["visible"])
        self.assertTrue(mir["visible"])
        self.assertTrue(again["visible"])
        self.assertEqual(created, ["de_dust2", "de_mirage"])
        self.assertEqual(backend.create_counts["de_dust2"], 1)
        self.assertEqual(backend.create_counts["de_mirage"], 1)
        # Only the active map remains cached.
        self.assertEqual(sorted(backend._cache.keys()), ["de_mirage"])

    def test_missing_tri_keeps_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = GeometryVisibilityBackend(
                tris_dir=Path(tmp),
                checker_factory=lambda _p: FakeVisibilityChecker(True),
            )
            out = backend.is_visible("de_dust2", (0, 0, 0), (1, 0, 0))
        self.assertEqual(out["status"], cfg.GEOMETRY_STATUS_TRI_MISSING)
        self.assertEqual(out["visible"], "Unavailable")

    def test_result_does_not_retain_tick_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "de_dust2.tri").write_bytes(b"tri")
            backend = GeometryVisibilityBackend(
                tris_dir=root,
                checker_factory=lambda _p: FakeVisibilityChecker(True),
            )
            rows = [{
                "tick": 1,
                "steamid": "1",
                "team_num": 2,
                "X": 0.0, "Y": 0.0, "Z": 0.0,
                "pitch": 0.0, "yaw": 0.0,
                "is_alive": True, "health": 100, "life_state": 0,
                "approximate_spotted_by": [], "ducked": False, "ducking": False, "fov": 0,
            }]
            out = va.compute_visibility_agreement(
                map_name="de_dust2",
                shooter_steamid="1",
                shot_ticks=[1],
                tick_rows=rows,
                backend=backend,
            )
        self.assertNotIn("tick_rows", out)
        self.assertNotIn("rows", out)
        blob = str(out)
        self.assertNotIn("'X':", blob)

    def test_v2_unchanged_with_windowed_contexts(self) -> None:
        ctx = {
            "is_rifle": True,
            "is_ak": True,
            "is_m4": False,
            "crouch": False,
            "engagement_verified": True,
            "max_speed": 215.0,
            "velocity": 0.0,
            "speed_ratio": 0.1,
            "is_first_bullet": True,
            "eligibility_source": cfg.V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED,
            "evidence_bucket": cfg.V2_EVIDENCE_SPOTTED_ONLY,
            "weapon": "ak47",
        }
        result = compute_proper_counter_strafe_v2([ctx])
        self.assertEqual(result["measurement_quality"], cfg.V2_MEASUREMENT_QUALITY_EXPERIMENTAL)
        self.assertEqual(result["eligible_shots"], 1)
        self.assertEqual(result["proper_counter_strafe_pct"], 100.0)

    def test_no_network_or_db(self) -> None:
        with patch("src.storage._connect", side_effect=AssertionError("DB")):
            with patch("requests.Session.get", side_effect=AssertionError("NET")):
                window = collect_shot_tick_window([{"tick": 5}], tolerance=1)
        self.assertEqual(window, [4, 5, 6])


if __name__ == "__main__":
    unittest.main()
