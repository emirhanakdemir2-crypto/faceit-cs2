from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEWER_WEB = REPO_ROOT / "third_party" / "cs2-2d-demo-viewer" / "web"
VIEWER_SRC = VIEWER_WEB / "src" / "Player"


class ReplayMapContextIsolationTests(unittest.TestCase):
    def test_viewer_sources_do_not_reference_h4_geometry(self) -> None:
        forbidden = (
            "geometry_visibility",
            "visibility_agreement",
            "VisibilityChecker",
            "awpy",
        )
        for path in VIEWER_SRC.rglob("*"):
            if path.suffix not in {".js", ".jsx", ".css"}:
                continue
            content = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(
                    token,
                    content,
                    msg=f"{path.relative_to(REPO_ROOT)} must not reference {token}",
                )


class ReplayMapContextViewerTests(unittest.TestCase):
    def test_upstream_vitest_suite_passes(self) -> None:
        if not (VIEWER_WEB / "node_modules").is_dir():
            self.skipTest("viewer node_modules not installed")
        result = subprocess.run(
            ["npm", "test"],
            cwd=VIEWER_WEB,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=True,
        )
        output = (result.stdout or "") + (result.stderr or "")
        self.assertEqual(result.returncode, 0, msg=output)


if __name__ == "__main__":
    unittest.main()
