from __future__ import annotations

import unittest

from src.map_manifest import (
    COORDINATE_FRAME,
    REQUIRED_MANIFEST_FIELDS,
    UNITS,
    build_manifest,
    validate_manifest,
)


def build_dust2_shape_manifest() -> dict:
    return {
        "schemaVersion": 1,
        "mapName": "de_dust2",
        "source": "user_exported_from_local_cs2_install",
        "sourceTool": "Source 2 Viewer",
        "sourceClientVersion": "2000877",
        "coordinateFrame": COORDINATE_FRAME,
        "units": UNITS,
        "viewerTransformVersion": 1,
        "sceneFile": "scene.glb",
        "sceneSha256": "2c48aa6efe3d13a530ea2ffa107c3921d517afe1374a4da4aeeb6193b367e60d",
        "generatedAt": "2026-07-26T23:45:25.7175163Z",
        "licenseNotice": "Local user-provided game asset; do not commit or redistribute.",
    }


class MapManifestContractTests(unittest.TestCase):
    def test_required_fields_match_viewer_contract(self) -> None:
        self.assertEqual(
            REQUIRED_MANIFEST_FIELDS,
            (
                "schemaVersion",
                "mapName",
                "source",
                "sourceTool",
                "coordinateFrame",
                "units",
                "viewerTransformVersion",
                "sceneFile",
                "licenseNotice",
            ),
        )

    def test_build_manifest_matches_contract(self) -> None:
        manifest = build_manifest("de_ancient", source_client_version="1.2.3")
        result = validate_manifest(manifest, expected_map_name="de_ancient")
        self.assertTrue(result.ok)

    def test_dust2_shape_fixture_validates(self) -> None:
        result = validate_manifest(build_dust2_shape_manifest(), expected_map_name="de_dust2")
        self.assertTrue(result.ok)

    def test_rejects_wrong_map_name(self) -> None:
        manifest = build_manifest("de_ancient")
        result = validate_manifest(manifest, expected_map_name="de_mirage")
        self.assertFalse(result.ok)

    def test_rejects_wrong_scene_file(self) -> None:
        manifest = build_manifest("de_ancient")
        manifest["sceneFile"] = "other.glb"
        result = validate_manifest(manifest, expected_map_name="de_ancient")
        self.assertFalse(result.ok)

    def test_rejects_path_traversal_scene_file(self) -> None:
        manifest = build_manifest("de_ancient")
        manifest["sceneFile"] = "../scene.glb"
        result = validate_manifest(manifest, expected_map_name="de_ancient")
        self.assertFalse(result.ok)

    def test_rejects_wrong_coordinate_frame(self) -> None:
        manifest = build_manifest("de_ancient")
        manifest["coordinateFrame"] = "legacy_radar_percent"
        result = validate_manifest(manifest, expected_map_name="de_ancient")
        self.assertFalse(result.ok)

    def test_rejects_wrong_units(self) -> None:
        manifest = build_manifest("de_ancient")
        manifest["units"] = "meters"
        result = validate_manifest(manifest, expected_map_name="de_ancient")
        self.assertFalse(result.ok)

    def test_rejects_malformed_scene_sha256(self) -> None:
        manifest = build_manifest("de_ancient", scene_sha256="not-a-sha256")
        result = validate_manifest(manifest, expected_map_name="de_ancient")
        self.assertFalse(result.ok)
        self.assertIn("sceneSha256", result.errors[0])


if __name__ == "__main__":
    unittest.main()
