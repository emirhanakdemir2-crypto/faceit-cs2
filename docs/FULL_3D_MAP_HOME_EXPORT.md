# Full 3D Map — Home Export Guide

This workflow runs **only on a personal PC with CS2 installed**. Do not commit or redistribute extracted Valve assets.

## Prerequisites (home PC)

- Steam + Counter-Strike 2
- [Source 2 Viewer](https://s2v.app/) (MIT-licensed tool; exported CS2 assets remain Valve property)
- PowerShell
- Optional optimization CLI (checked by script, **not auto-installed**):
  - **gltfpack** (Meshoptimizer, MIT) — preferred for fast GLB compression
  - or **gltf-transform** (MIT)
  - or **Blender CLI** (GPL — use only if already installed)

## Export steps

1. Locate map VPK, e.g. `game/csgo/maps/de_ancient.vpk`
2. Do **not** use `_vanity` maps.
3. Open the real `.vmap_c` inside the VPK in Source 2 Viewer.
4. Choose **Decompile & Export**.
5. Prefer **glTF** for large maps; single **GLB** is limited (~2 GB practical browser limit).
6. Export includes geometry, textures, props, and basic materials.
7. Copy export folder to:

   ```text
   data/maps3d/source/de_ancient/
   ```

8. Run preparation script from repo root:

   ```powershell
   .\scripts\prepare_cs2_map_asset.ps1 -MapName de_ancient -SourcePath "D:\exports\de_ancient_gltf" -ClientVersion "1.0.0.0"
   ```

   Dry run:

   ```powershell
   .\scripts\prepare_cs2_map_asset.ps1 -MapName de_ancient -SourcePath "D:\exports\de_ancient_gltf" -WhatIf
   ```

9. Output:

   ```text
   data/maps3d/optimized/de_ancient/scene.glb
   data/maps3d/optimized/de_ancient/manifest.json
   ```

## Viewer smoke test

From repo root (with local map assets present):

```powershell
python -m src.main --nickname YourName --replay-demo data/demos/your_demo.dem
```

Open 3D trajectory modal → **Scene: Full 3D map**.

## Safety rules

- Never `git add` files under `data/maps3d/`
- Never redistribute Valve textures/models
- Keep backups; optimized GLB can be multi-GB
- Record `-ClientVersion` in manifest for mismatch warnings

## Optimization backend decision

| Tool | License | Role |
| --- | --- | --- |
| **gltfpack** | MIT | Preferred fast mesh/texture compression to GLB |
| gltf-transform | MIT | Alternative pipeline |
| Blender CLI | GPL | Fallback only if already installed |

The preparation script stops with a clear error if no tool is installed. It does **not** download tools automatically.

## Legal note

Source 2 Viewer may be MIT-licensed, but exported CS2 map content is **Valve intellectual property** for personal/local use only.
