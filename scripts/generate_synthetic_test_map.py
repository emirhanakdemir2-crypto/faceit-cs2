#!/usr/bin/env python3
"""Generate a tiny synthetic GLB fixture for local map pipeline tests."""

from __future__ import annotations

import json
import struct
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "tests" / "fixtures" / "synthetic_test_arena"


def _padded(data: bytes, alignment: int = 4) -> bytes:
    pad = (alignment - (len(data) % alignment)) % alignment
    return data + (b"\x00" * pad)


def build_minimal_glb() -> bytes:
    # Single triangle on Z=0 plane in Source2-style coordinates.
    positions = struct.pack("<9f", 0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 100.0, 0.0)
    indices = struct.pack("<3H", 0, 1, 2)
    bin_blob = _padded(positions + indices)

    gltf = {
        "asset": {"version": "2.0", "generator": "synthetic_test_map_generator"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "indices": 1,
                    }
                ]
            }
        ],
        "buffers": [{"byteLength": len(bin_blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions), "target": 34962},
            {"buffer": 0, "byteOffset": len(positions), "byteLength": len(indices), "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "max": [100.0, 100.0, 0.0],
                "min": [0.0, 0.0, 0.0],
            },
            {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
    }

    json_chunk = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_chunk = _padded(json_chunk)
    bin_chunk = _padded(bin_blob)

    header = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(json_chunk) + 8 + len(bin_chunk))
    json_header = struct.pack("<I4s", len(json_chunk), b"JSON")
    bin_header = struct.pack("<I4s", len(bin_chunk), b"BIN\x00")
    return header + json_header + json_chunk + bin_header + bin_chunk


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    glb_path = OUTPUT_DIR / "scene.glb"
    glb_path.write_bytes(build_minimal_glb())
    manifest = {
        "schemaVersion": 1,
        "mapName": "synthetic_test_arena",
        "source": "project_generated_fixture",
        "sourceTool": "synthetic_test_map_generator",
        "sourceClientVersion": None,
        "coordinateFrame": "source2_world_z_up",
        "units": "hammer_units",
        "viewerTransformVersion": 1,
        "sceneFile": "scene.glb",
        "sceneSha256": None,
        "generatedAt": None,
        "licenseNotice": "Synthetic test geometry; not a Valve asset.",
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote synthetic fixture to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
