# Coordinate Audit — Full 3D Map Pipeline Phase 0

## Summary

Grenade trajectory data previously mixed **radar percent X/Y (0–100)** with **raw world Z**. Full 3D map meshes require a single Source 2 world frame. Phase A adds parallel raw world fields and a viewer transform helper without breaking 2D replay.

## Findings

### 1. Go parser projectile world X/Y/Z

Source: `demoinfocs` `r3.Vector` from `proj.Position()` and trajectory entries.

- Units: Source 2 Hammer world units
- Axes: X/Y horizontal, **Z up**

### 2. `translatePosition()` application

- Player positions: `parser.go` → `transformPlayer()` → radar percent via map overview scale
- Grenades: `grenade_trajectory.go` → `worldToPercent()` → same percent transform for X/Y; **Z left as raw world height**

### 3. Protobuf before Phase A

| Field | Meaning |
| --- | --- |
| `TrajectoryPoint.x/y` | Radar percent 0–100 |
| `TrajectoryPoint.z` | Raw world Z |
| `GrenadeTrajectory.originX/Y`, `detonationX/Y` | Radar percent |
| `GrenadeTrajectory.originZ`, `detonationZ` | Raw world Z |

### 4. Utility 2D overlay

`utilityInspector.js` → `normalizeTrajectoryMessage()` uses `x/y` as radar percent; `utilityOverlay.js` draws in SVG 0–100 viewBox.

### 5. 3D trajectory (radar-plane mode)

`trajectory3dCoords.js` maps radar percent to a 100×100 plane; Z uses `TRAJECTORY_Z_UNIT_SCALE = 0.2`.

### 6. H4 / Awpy geometry

Parent tests forbid shipping Awpy collision geometry as a textured map in the viewer. No Awpy mesh is loaded in the viewer today.

### 7. Source 2 glTF export (expected)

Source 2 Viewer exports geometry in **Source 2 world space, Z-up**. Viewer converts once via `source2WorldToThreeJs()`:

```
sceneX = worldX
sceneY = worldZ
sceneZ = -worldY
```

Basis tests live in `worldCoordinates.test.js`.

### 8. Map overview metadata

`parser/pkg/parser/map.go` — `MapCS` with `PZero` and `Scale` from CS overview `.txt`. `translatePosition()` divides translated pixel coords by 1024×100 for percent.

## Target contract

```
Demo world frame:
  X/Y/Z = Source 2 Hammer world units, Z-up

Viewer:
  Source 2 Z-up → Three.js Y-up (single helper)
```

## Phase A protobuf additions

Parallel fields (2D fields unchanged):

- `TrajectoryPoint.worldX/Y/Z`
- `BouncePoint.worldX/Y/Z`
- `GrenadeTrajectory.originWorldX/Y/Z`, `detonationWorldX/Y/Z`

Missing raw values are **not** inferred in the viewer.
