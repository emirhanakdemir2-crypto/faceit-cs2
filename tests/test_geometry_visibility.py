from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import geometry_visibility as gv
from src import suite_config as cfg


class GeometryVisibilityBackendTests(unittest.TestCase):
    def test_dependency_missing_status(self) -> None:
        with patch.dict("sys.modules", {"awpy": None, "awpy.visibility": None, "awpy.data": None}):
            with patch(
                "src.geometry_visibility.awpy_import_status",
                return_value={
                    "ok": False,
                    "version": gv.UNAVAILABLE,
                    "tris_dir": gv.UNAVAILABLE,
                    "status": cfg.GEOMETRY_STATUS_DEPENDENCY_MISSING,
                    "error": "No module named awpy",
                    "setup_command": cfg.GEOMETRY_SETUP_COMMAND,
                },
            ):
                resolved = gv.resolve_tri_path("de_dust2", require_awpy=True)
        self.assertEqual(resolved["status"], cfg.GEOMETRY_STATUS_DEPENDENCY_MISSING)
        self.assertEqual(resolved["setup_command"], cfg.GEOMETRY_SETUP_COMMAND)

    def test_tri_missing_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolved = gv.resolve_tri_path(
                "de_dust2", tris_dir=root, require_awpy=False,
            )
        self.assertEqual(resolved["status"], cfg.GEOMETRY_STATUS_TRI_MISSING)
        self.assertIn("awpy get tris", resolved["setup_command"])

    def test_unsupported_map_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "de_dust2.tri").write_bytes(b"x")
            resolved = gv.resolve_tri_path(
                "de_unknown_workshop", tris_dir=root, require_awpy=False,
            )
        self.assertEqual(resolved["status"], cfg.GEOMETRY_STATUS_UNSUPPORTED_MAP)
        self.assertIn("de_dust2", resolved.get("available_maps") or [])

    def test_checker_created_once_per_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "de_mirage.tri").write_bytes(b"tri")
            creates: list[str] = []

            def factory(path: Path):
                creates.append(path.stem)
                return gv.FakeVisibilityChecker(True)

            backend = gv.GeometryVisibilityBackend(
                tris_dir=root,
                checker_factory=factory,
                backend_source="fake",
                backend_version="test",
            )
            for _ in range(5):
                out = backend.is_visible(
                    "de_mirage", (0.0, 0.0, 64.0), (100.0, 0.0, 64.0),
                )
                self.assertTrue(out["visible"])
            self.assertEqual(creates, ["de_mirage"])
            self.assertEqual(backend.create_counts.get("de_mirage"), 1)

    def test_visible_and_blocked_fake_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "de_dust2.tri").write_bytes(b"tri")

            def factory(_path: Path):
                return gv.FakeVisibilityChecker(
                    lambda start, end: end[0] > 50,
                )

            backend = gv.GeometryVisibilityBackend(
                tris_dir=root, checker_factory=factory,
            )
            vis = backend.is_visible("de_dust2", (0, 0, 0), (100, 0, 0))
            blocked = backend.is_visible("de_dust2", (0, 0, 0), (10, 0, 0))
        self.assertTrue(vis["visible"])
        self.assertFalse(blocked["visible"])
        self.assertEqual(vis["measurement_quality"], cfg.GEOMETRY_MEASUREMENT_QUALITY)
        self.assertNotEqual(vis["measurement_quality"], "validated")

    def test_init_failed_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "de_inferno.tri").write_bytes(b"tri")

            def factory(_path: Path):
                raise RuntimeError("bvh boom")

            backend = gv.GeometryVisibilityBackend(
                tris_dir=root, checker_factory=factory,
            )
            status = backend.ensure_map("de_inferno")
        self.assertEqual(status["status"], cfg.GEOMETRY_STATUS_INIT_FAILED)

    def test_no_network_or_tri_download_in_unit_path(self) -> None:
        with patch("requests.Session.get", side_effect=AssertionError("NET")):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "de_nuke.tri").write_bytes(b"tri")
                backend = gv.GeometryVisibilityBackend(
                    tris_dir=root,
                    checker_factory=lambda _p: gv.FakeVisibilityChecker(False),
                )
                out = backend.is_visible("de_nuke", (1, 2, 3), (4, 5, 6))
        self.assertIs(out["visible"], False)


if __name__ == "__main__":
    unittest.main()
