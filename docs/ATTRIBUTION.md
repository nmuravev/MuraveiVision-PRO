# AliceVision / Meshroom third-party attribution (MPL-2.0)

## AliceVision

- **Project:** [AliceVision](https://alicevision.org/) photogrammetry framework
- **License:** Mozilla Public License 2.0 (MPL-2.0)
- **Sidecar copy:** `sidecars/alicevision/LICENSE.MPL-2.0`
- **Pinned Windows build:** see `scripts/alicevision_manifest.json` (`chosen.version`, URL, SHA256)
- **Role in MuraveiVision PRO:** optional dense MVS + textured mesh after COLMAP sparse SfM (v3.2+)

MuraveiVision does **not** replace COLMAP SfM with AliceVision. AliceVision is used only when Dense / Mesh presets are selected and the sidecar + CUDA are available.

Upstream NOTICE / copyright remain with the AliceVision authors and contributors. Redistribution of the Windows binary sidecar in Full portable kits must retain `LICENSE.MPL-2.0` and this attribution.
