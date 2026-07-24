from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

import urllib.request

from src.map_asset_server import (
    MapAssetServer,
    MapAssetServerError,
    parse_map_asset_path,
    resolve_map_asset_file,
)
from src.map_manifest import build_manifest, sha256_file, validate_map_asset_dir


class MapAssetServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.optimized = self.root / "optimized"
        self.optimized.mkdir(parents=True)
        self.map_dir = self.optimized / "synthetic_test_arena"
        self.map_dir.mkdir()
        self.scene_bytes = b"glTF synthetic fixture"
        (self.map_dir / "scene.glb").write_bytes(self.scene_bytes)
        manifest = build_manifest(
            "synthetic_test_arena",
            scene_sha256=sha256_file(self.map_dir / "scene.glb"),
        )
        (self.map_dir / "manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        self.server = MapAssetServer(self.optimized, host="127.0.0.1", port=0)
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()
        self._tmpdir.cleanup()

    def _fetch(self, path: str, headers: dict[str, str] | None = None) -> tuple[int, bytes, dict[str, str]]:
        request = urllib.request.Request(f"{self.server.base_url}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read()
                response_headers = dict(response.headers.items())
                return response.status, body, response_headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), dict(exc.headers.items())

    def test_valid_glb_access(self) -> None:
        status, body, headers = self._fetch("/local-map-assets/synthetic_test_arena/scene.glb")
        self.assertEqual(status, 200)
        self.assertEqual(body, self.scene_bytes)
        self.assertEqual(headers.get("Content-Type"), "model/gltf-binary")

    def test_valid_manifest_access(self) -> None:
        status, body, _ = self._fetch("/local-map-assets/synthetic_test_arena/manifest.json")
        self.assertEqual(status, 200)
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["mapName"], "synthetic_test_arena")

    def test_path_traversal_rejected(self) -> None:
        status, _, _ = self._fetch("/local-map-assets/synthetic_test_arena/../secret/scene.glb")
        self.assertEqual(status, 404)

    def test_other_data_files_rejected(self) -> None:
        secret = self.root / "secret.txt"
        secret.write_text("secret", encoding="utf-8")
        status, _, _ = self._fetch("/local-map-assets/secret.txt/scene.glb")
        self.assertEqual(status, 404)

    def test_directory_listing_rejected(self) -> None:
        status, _, _ = self._fetch("/local-map-assets/synthetic_test_arena/")
        self.assertEqual(status, 404)

    def test_missing_asset(self) -> None:
        status, _, _ = self._fetch("/local-map-assets/de_mirage/scene.glb")
        self.assertEqual(status, 404)

    def test_invalid_map_name(self) -> None:
        status, _, _ = self._fetch("/local-map-assets/not-a-map/scene.glb")
        self.assertEqual(status, 404)

    def test_range_request_supported(self) -> None:
        status, body, headers = self._fetch(
            "/local-map-assets/synthetic_test_arena/scene.glb",
            headers={"Range": "bytes=0-4"},
        )
        self.assertEqual(status, 206)
        self.assertEqual(body, self.scene_bytes[:5])
        self.assertIn("Content-Range", headers)

    def test_manifest_validation(self) -> None:
        result = validate_map_asset_dir(self.optimized, "synthetic_test_arena")
        self.assertTrue(result.ok)

    def test_parse_route_helper(self) -> None:
        self.assertEqual(
            parse_map_asset_path("/local-map-assets/synthetic_test_arena/scene.glb"),
            ("synthetic_test_arena", "scene.glb"),
        )
        self.assertIsNone(parse_map_asset_path("/local-map-assets/synthetic_test_arena/extra/scene.glb"))

    def test_resolve_helper_blocks_escape(self) -> None:
        self.assertIsNone(resolve_map_asset_file(self.optimized, "../secret", "scene.glb"))

    def test_loopback_bind_required(self) -> None:
        with self.assertRaises(MapAssetServerError):
            MapAssetServer(self.optimized, host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
