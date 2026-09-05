# AliceVision dense photogrammetry (v3.2)

Optional **dense MVS + textured mesh** after COLMAP sparse SfM. AliceVision does **not** replace COLMAP.

## Capabilities

| Preset | Backend | Output | Needs |
|--------|---------|--------|--------|
| Sparse | `colmap_only` | `sparse_points.json` (already from Build3D) | COLMAP |
| Dense | `alicevision_mvs` | `dense_point_cloud.ply` | AliceVision sidecar + **NVIDIA CUDA** (≥6 GB VRAM) |
| Mesh | `alicevision_mesh` | `textured_mesh.obj` (+ `.mtl` / textures) | AliceVision + CUDA (≥8 GB VRAM) |
| Splat | `gsplat` | `model.ply` | CUDA + MSVC (as before) |

Aliases: `bootstrap`→sparse/bootstrap script, `balanced`/`high`→splat.

## Pipeline (after COLMAP)

1. Copy HUD-masked frames → `alicevision_input/` (originals under `frames/` untouched)
2. `cameraInit` → inject COLMAP poses into `.sfm`
3. `prepareDenseScene` → `depthMapEstimation` → `depthMapFiltering` → `meshing`
4. Dense: export PLY; Mesh: `meshFiltering` + `texturing`

On failure: sparse stays intact; `manifest.alicevision_warning` + train channel error. Never wipe COLMAP.

## Sidecar

- Manifest: [`scripts/alicevision_manifest.json`](../scripts/alicevision_manifest.json) (version **3.3.0**, SHA256, tool list)
- Layout: `sidecars/alicevision/windows-x64/{bin,lib,share}` (gitignored binaries)
- Fetch (offline build machine): `scripts/fetch_alicevision.ps1` / `.sh` — **do not** auto-download at runtime
- Env: `ALICEVISION_ROOT` → platform root containing `bin/` (launchers set this when present)
- License: MPL-2.0 — see [ATTRIBUTION.md](ATTRIBUTION.md) and `sidecars/alicevision/LICENSE.MPL-2.0`

## CUDA honesty

Shipping AliceVision `depthMapEstimation` is CUDA/NVIDIA-backed. **No reliable CPU fallback.** Dense/Mesh presets show Russian `disabled_reason` when sidecar missing or CUDA unavailable.

## Comparison

| | Sparse COLMAP | Dense AV | Mesh AV | Splat gsplat |
|--|---------------|----------|---------|--------------|
| Photorealism | low | medium (points) | medium–high (textured) | high (Gaussian) |
| GPU | optional for SfM | **required** | **required** | required |
| Typical ETA | Build3D only | 10–40 мин | 20–60 мин | 5–30 мин |
| Portable | FullKit COLMAP | FullKit optional AV | same | FullKit gsplat |

## Portable

FullKit copies AliceVision when `windows-x64/bin` is staged (`-IncludeAliceVision` / default-on if present; `-NoAliceVision` to skip). Mini never bundles it. See [PORTABLE.md](PORTABLE.md).

## Operator path

Flight3D → Build3D (sparse) → hierarchy **Sparse / Dense / Mesh / Splat** → artifact selector «Показать» → export per artifact (mesh = ZIP).
