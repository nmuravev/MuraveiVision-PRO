# AliceVision / Meshroom / DA3 third-party attribution

## 1. Depth Anything 3 (DA3)

- **Project:** [Depth Anything 3 (DA3)](https://github.com/bytedance-seed/depth-anything-3)
- **Role in MuraveiVision PRO:** default neural Dense backend after COLMAP (`da3_dense_base` / `large` / `metric` / `giant`); AliceVision is Mesh-only (opt-in)
- **Licenses (per upstream model cards):**
  - **DA3-BASE / DA3-METRIC (DA3METRIC-LARGE):** Apache License 2.0
  - **DA3-LARGE / DA3-GIANT:** Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
- **Sidecar / Weights location:** `sidecars/da3/` (FullKit-only; never under `assets/models/` — Mini pack size)
- **Fetch / stage:** `scripts/fetch_da3_weights.py` + `scripts/stage_da3_sidecar.ps1` read **only** `scripts/portable_manifest.json` → `sidecars.da3` (Z1)
- **Non-Commercial Notice:** FullKit stage with NC weights must include `sidecars/da3/NOTICE_CC-BY-NC-4.0.txt`; UI shows NC badge for `da3_dense_large` / `da3_dense_giant`
- **Non-commercial project declaration:** MuraveiVision PRO is an open non-commercial project. CC BY-NC 4.0 artifacts in the FullKit sidecar (DA3-LARGE, DA3-GIANT + NOTICE) are supplied only under that NC declaration; commercial use of those weights is not permitted.
- **Citation:** arXiv:2511.10647

## 2. AliceVision

- **Project:** [AliceVision](https://alicevision.org/) photogrammetry framework
- **License:** Mozilla Public License 2.0 (MPL-2.0)
- **Sidecar copy:** `sidecars/alicevision/LICENSE.MPL-2.0`
- **Pinned Windows build:** see `scripts/alicevision_manifest.json` (`chosen.version`, URL, SHA256)
- **Role in MuraveiVision PRO:** Mesh-only opt-in backend (textured mesh OBJ+MTL) after COLMAP + DA3 Dense; AliceVision MVS Dense is legacy behind `MURAVEI_LEGACY_AV_DENSE=1`

MuraveiVision does **not** replace COLMAP SfM with AliceVision or DA3. Dense backends run only when Dense / Mesh / DA3 presets are selected and sidecars + CUDA are available.

Upstream NOTICE / copyright remain with the respective authors. Redistribution of Windows binary sidecars in Full portable kits must retain license files and this attribution.
