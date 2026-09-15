# AliceVision / Meshroom / DA3 third-party attribution

## 1. Depth Anything 3 (DA3)

- **Project:** [Depth Anything 3 (DA3)](https://github.com/bytedance-seed/depth-anything-3)
- **Role in MuraveiVision PRO:** optional neural Dense backend after COLMAP (`da3_dense_base` / `da3_dense_large`)
- **Licenses (per upstream model cards):**
  - **DA3-BASE:** Apache License 2.0
  - **DA3-LARGE / Giant / Nested series:** Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
- **Sidecar / Weights location:** `sidecars/da3/` (FullKit-only; never under `assets/models/` — Mini pack size)
- **Fetch / stage:** `scripts/fetch_da3_weights.py` + `scripts/stage_da3_sidecar.ps1` read **only** `scripts/portable_manifest.json` → `sidecars.da3` (Z1)
- **Non-Commercial Notice:** distributions incorporating DA3-LARGE (CC BY-NC) must retain Non-Commercial constraints; UI shows NC badge for `da3_dense_large`

## 2. AliceVision

- **Project:** [AliceVision](https://alicevision.org/) photogrammetry framework
- **License:** Mozilla Public License 2.0 (MPL-2.0)
- **Sidecar copy:** `sidecars/alicevision/LICENSE.MPL-2.0`
- **Pinned Windows build:** see `scripts/alicevision_manifest.json` (`chosen.version`, URL, SHA256)
- **Role in MuraveiVision PRO:** optional dense MVS + textured mesh after COLMAP sparse SfM (v3.2+)

MuraveiVision does **not** replace COLMAP SfM with AliceVision or DA3. Dense backends run only when Dense / Mesh / DA3 presets are selected and sidecars + CUDA are available.

Upstream NOTICE / copyright remain with the respective authors. Redistribution of Windows binary sidecars in Full portable kits must retain license files and this attribution.
