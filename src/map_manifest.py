from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAP_NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")
ALLOWED_MAP_NAMES = frozenset(
    {
        "de_ancient",
        "de_anubis",
        "de_dust2",
        "de_inferno",
        "de_mirage",
        "de_nuke",
        "de_overpass",
        "de_train",
        "de_vertigo",
        "cs_office",
        "synthetic_test_arena",
    }
)
COORDINATE_FRAME = "source2_world_z_up"
UNITS = "hammer_units"
LICENSE_NOTICE = (
    "Local user-provided game asset; do not commit or redistribute."
)
REQUIRED_MANIFEST_FIELDS = (
    "schemaVersion",
    "mapName",
    "source",
    "sourceTool",
    "coordinateFrame",
    "units",
    "viewerTransformVersion",
    "sceneFile",
    "licenseNotice",
)


@dataclass(frozen=True)
class MapManifestValidation:
    ok: bool
    manifest: dict[str, Any] | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def is_valid_map_name(map_name: str) -> bool:
    if not map_name or not MAP_NAME_PATTERN.fullmatch(map_name):
        return False
    return map_name in ALLOWED_MAP_NAMES


def safe_map_dir(root: Path, map_name: str) -> Path | None:
    if not is_valid_map_name(map_name):
        return None
    candidate = (root / map_name).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None
    return candidate


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_manifest(
    manifest: dict[str, Any],
    *,
    expected_map_name: str | None = None,
    scene_path: Path | None = None,
    expected_client_version: str | None = None,
) -> MapManifestValidation:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(manifest, dict):
        return MapManifestValidation(ok=False, errors=("manifest must be a JSON object",))

    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            errors.append(f"missing required field: {field}")

    map_name = str(manifest.get("mapName", ""))
    if not is_valid_map_name(map_name):
        errors.append(f"invalid mapName: {map_name!r}")
    if expected_map_name and map_name != expected_map_name:
        errors.append(
            f"manifest mapName {map_name!r} does not match folder {expected_map_name!r}"
        )

    if manifest.get("coordinateFrame") != COORDINATE_FRAME:
        errors.append("coordinateFrame must be source2_world_z_up")
    if manifest.get("units") != UNITS:
        errors.append("units must be hammer_units")

    scene_file = str(manifest.get("sceneFile", ""))
    if scene_file != "scene.glb":
        errors.append("sceneFile must be scene.glb")
    if ".." in scene_file or scene_file.startswith(("/", "\\")):
        errors.append("sceneFile must be a relative file name")

    manifest_client = manifest.get("sourceClientVersion")
    if expected_client_version and manifest_client not in (None, expected_client_version):
        warnings.append(
            f"sourceClientVersion mismatch: manifest={manifest_client!r} expected={expected_client_version!r}"
        )

    scene_sha = manifest.get("sceneSha256")
    if scene_path and scene_path.is_file():
        actual_sha = sha256_file(scene_path)
        if scene_sha and scene_sha != actual_sha:
            errors.append("sceneSha256 does not match scene.glb contents")
    elif scene_sha:
        warnings.append("sceneSha256 present but scene.glb missing")

    if errors:
        return MapManifestValidation(ok=False, manifest=manifest, errors=tuple(errors), warnings=tuple(warnings))
    return MapManifestValidation(ok=True, manifest=manifest, warnings=tuple(warnings))


def validate_map_asset_dir(
    optimized_root: Path,
    map_name: str,
    *,
    expected_client_version: str | None = None,
) -> MapManifestValidation:
    map_dir = safe_map_dir(optimized_root, map_name)
    if map_dir is None:
        return MapManifestValidation(ok=False, errors=("invalid map name",))

    manifest_path = map_dir / "manifest.json"
    scene_path = map_dir / "scene.glb"
    if not manifest_path.is_file():
        return MapManifestValidation(ok=False, errors=("manifest.json missing",))
    if not scene_path.is_file():
        return MapManifestValidation(ok=False, errors=("scene.glb missing",))

    try:
        manifest = load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        return MapManifestValidation(ok=False, errors=(f"manifest parse error: {exc}",))

    return validate_manifest(
        manifest,
        expected_map_name=map_name,
        scene_path=scene_path,
        expected_client_version=expected_client_version,
    )


def build_manifest(
    map_name: str,
    *,
    source_client_version: str | None = None,
    scene_sha256: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if not is_valid_map_name(map_name):
        raise ValueError(f"invalid map name: {map_name}")
    return {
        "schemaVersion": 1,
        "mapName": map_name,
        "source": "user_exported_from_local_cs2_install",
        "sourceTool": "Source 2 Viewer",
        "sourceClientVersion": source_client_version,
        "coordinateFrame": COORDINATE_FRAME,
        "units": UNITS,
        "viewerTransformVersion": 1,
        "sceneFile": "scene.glb",
        "sceneSha256": scene_sha256,
        "generatedAt": generated_at,
        "licenseNotice": LICENSE_NOTICE,
    }
