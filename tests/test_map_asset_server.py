from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

import urllib.request

from src.map_asset_server import (
    CORS_ALLOW_HEADERS,
    CORS_EXPOSE_HEADERS,
    MapAssetServer,
    MapAssetServerError,
    cors_allow_origin,
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

    def test_cors_allows_loopback_viewer_origin(self) -> None:
        status, _, headers = self._fetch(
            "/local-map-assets/synthetic_test_arena/manifest.json",
            headers={"Origin": "http://127.0.0.1:3000"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:3000")
        self.assertEqual(headers.get("Vary"), "Origin")
        self.assertEqual(headers.get("Access-Control-Expose-Headers"), CORS_EXPOSE_HEADERS)
        self.assertNotIn("Access-Control-Allow-Methods", headers)

    def test_cors_allows_dynamic_loopback_port(self) -> None:
        status, _, headers = self._fetch(
            "/local-map-assets/synthetic_test_arena/manifest.json",
            headers={"Origin": "http://127.0.0.1:64221"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:64221")

    def test_cors_allows_localhost_origin(self) -> None:
        status, _, headers = self._fetch(
            "/local-map-assets/synthetic_test_arena/manifest.json",
            headers={"Origin": "http://localhost:3002"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "http://localhost:3002")

    def test_cors_blocks_non_loopback_origin(self) -> None:
        status, _, headers = self._fetch(
            "/local-map-assets/synthetic_test_arena/manifest.json",
            headers={"Origin": "https://example.com"},
        )
        self.assertEqual(status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_cors_blocks_evil_subdomain_origin(self) -> None:
        status, _, headers = self._fetch(
            "/local-map-assets/synthetic_test_arena/manifest.json",
            headers={"Origin": "http://127.0.0.1.evil.example:3002"},
        )
        self.assertEqual(status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_cors_glb_range_includes_expose_headers(self) -> None:
        status, body, headers = self._fetch(
            "/local-map-assets/synthetic_test_arena/scene.glb",
            headers={
                "Origin": "http://127.0.0.1:3002",
                "Range": "bytes=0-4",
            },
        )
        self.assertEqual(status, 206)
        self.assertEqual(body, self.scene_bytes[:5])
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:3002")
        self.assertEqual(headers.get("Vary"), "Origin")
        self.assertEqual(headers.get("Access-Control-Expose-Headers"), CORS_EXPOSE_HEADERS)
        self.assertIn("Content-Range", headers)

    def test_cors_preflight_for_range(self) -> None:
        request = urllib.request.Request(
            f"{self.server.base_url}/local-map-assets/synthetic_test_arena/scene.glb",
            method="OPTIONS",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "range",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            headers = dict(response.headers.items())
        self.assertEqual(response.status, 204)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:3000")
        self.assertEqual(headers.get("Vary"), "Origin")
        self.assertIn("GET", headers.get("Access-Control-Allow-Methods", ""))
        self.assertEqual(headers.get("Access-Control-Allow-Headers"), CORS_ALLOW_HEADERS)
        self.assertEqual(headers.get("Access-Control-Expose-Headers"), CORS_EXPOSE_HEADERS)

    def test_cors_preflight_private_network_access(self) -> None:
        request = urllib.request.Request(
            f"{self.server.base_url}/local-map-assets/synthetic_test_arena/manifest.json",
            method="OPTIONS",
            headers={
                "Origin": "http://127.0.0.1:3002",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "range",
                "Access-Control-Request-Private-Network": "true",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            headers = dict(response.headers.items())
        self.assertEqual(response.status, 204)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:3002")
        self.assertEqual(headers.get("Access-Control-Allow-Private-Network"), "true")

    def test_cors_allow_origin_helper(self) -> None:
        self.assertEqual(cors_allow_origin("http://127.0.0.1:3000"), "http://127.0.0.1:3000")
        self.assertEqual(cors_allow_origin("http://localhost:5173"), "http://localhost:5173")
        self.assertIsNone(cors_allow_origin("https://example.com"))
        self.assertIsNone(cors_allow_origin("http://127.0.0.1.evil.example:3002"))


if __name__ == "__main__":
    unittest.main()
