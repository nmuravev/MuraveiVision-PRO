# AliceVision Mesh-only backend (v3.4 demotion) & DA3 Dense

**Product rule:** Dense = **DA3 family**. AliceVision is the **opt-in textured Mesh** backend (spectral context: vegetation vs structure / camo-net). OBJ+MTL is the external GIS/CAD export path; splat remains view-dependent photorealism.

AliceVision does **not** replace COLMAP SfM. AliceVision MVS Dense (`preset=dense`) is **legacy** behind `MURAVEI_LEGACY_AV_DENSE=1`.

## Capabilities

| Preset | Backend | Output | Needs |
|--------|---------|--------|--------|
| Sparse | `colmap_only` | `sparse_points.json` | COLMAP |
| Dense (DA3-BASE) | `da3_dense_base` | `dense.ply` | `sidecars/da3/` Apache-2.0 + CUDA (≥6 GB) |
| Dense (DA3-LARGE) | `da3_dense_large` | `dense.ply` | NC weights + CUDA (≥8 GB) |
| Dense (DA3-METRIC) | `da3_dense_metric` | `dense.ply` | Apache metric weights + CUDA (≥8 GB) |
| Dense (DA3-GIANT) | `da3_dense_giant` | `dense.ply` | NC + CUDA (**≥16 GB**) |
| Dense (AV legacy) | `alicevision_mvs` | `dense_point_cloud.ply` | `MURAVEI_LEGACY_AV_DENSE=1` + AV sidecar + CUDA |
| Mesh | `alicevision_mesh` | `textured_mesh.obj` (+ `.mtl`) | AV sidecar + CUDA (≥8 GB) + `alicevision_enabled=1` |
| Splat | `gsplat` | `model.ply` | CUDA + MSVC |

Aliases: `bootstrap`→sparse, `balanced`/`high`→splat.

## Engineer toggle

SQLite setting `alicevision_enabled` (default `"1"`). UI: **Система → Конфигурация 3D**. When `"0"`, Mesh is grey with RU `disabled_reason`: «AliceVision отключён инженером».

## Pipeline (Mesh, after COLMAP + optional DA3)

1. Copy HUD-masked frames → `alicevision_input/`
2. `cameraInit` → inject COLMAP poses
3. `prepareDenseScene` → depth → `meshing` → `meshFiltering` + `texturing`

On failure: sparse stays intact; soft-fail gates unchanged (views &lt; 8, stub EXR, native abort).

## Sidecar / pack

- Windows-x64 only; fetch via `scripts/fetch_alicevision.ps1`.
- FullKit includes AV only when staged / `-IncludeAliceVision`; otherwise Mesh is unavailable (size saving).
- Mini never bundles AliceVision or DA3.

See also: [RECON_3D.md](RECON_3D.md), [KNOWN_ISSUES.md](KNOWN_ISSUES.md), [ATTRIBUTION.md](ATTRIBUTION.md).
