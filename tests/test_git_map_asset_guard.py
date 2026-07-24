from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from src.map_manifest import build_manifest, validate_manifest


class GitMapAssetGuardTests(unittest.TestCase):
    BLOCKED_SUFFIXES = (
        ".glb",
        ".gltf",
        ".bin",
        ".vpk",
        ".vmap",
        ".vmap_c",
    )
    ALLOWLIST_PREFIXES = (
        "tests/fixtures/synthetic_test_arena/",
        "scripts/generate_synthetic_test_map.py",
    )

    def _is_allowlisted(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        return any(normalized.startswith(prefix) for prefix in self.ALLOWLIST_PREFIXES)

    def _scan_staged_paths(self, repo_root: Path) -> list[str]:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def test_guard_detects_blocked_suffixes(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        staged = self._scan_staged_paths(repo_root)
        blocked = []
        for path in staged:
            if self._is_allowlisted(path):
                continue
            lower = path.lower()
            if any(lower.endswith(suffix) for suffix in self.BLOCKED_SUFFIXES):
                blocked.append(path)
        self.assertEqual(
            blocked,
            [],
            msg=f"Blocked map asset paths staged for commit: {blocked}",
        )

    def test_manifest_contract(self) -> None:
        manifest = build_manifest("de_ancient", source_client_version="1.2.3")
        result = validate_manifest(manifest, expected_map_name="de_ancient")
        self.assertTrue(result.ok)

    def test_manifest_rejects_traversal_in_scene_file(self) -> None:
        manifest = build_manifest("de_ancient")
        manifest["sceneFile"] = "../scene.glb"
        result = validate_manifest(manifest, expected_map_name="de_ancient")
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
