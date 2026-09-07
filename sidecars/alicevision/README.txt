AliceVision Windows sidecar (MuraveiVision PRO)
================================================

Version:  3.3.0 (AliceVision release v3.3.0, 2025-08-18)
Source:   alicevision/AliceVision (not Meshroom)
URL:      https://github.com/alicevision/AliceVision/releases/download/v3.3.0/AliceVision-3.3.0-Windows.zip
SHA256:   e6d6026faec6910541a1a9afcfad9aba6c10723bafccaacfc1378c49e6ab0c86
License:  MPL-2.0 (see LICENSE.MPL-2.0; upstream LICENSE-MPL2.md)

Layout (after extract + flatten)
--------------------------------
sidecars/alicevision/windows-x64/
  bin/     aliceVision_*.exe (108 tools) + dependent DLLs
  lib/     libraries
  share/   aliceVision/config.ocio and other data

Discovery should look under:
  sidecars/alicevision/windows-x64/bin/

Git hygiene
-----------
Binaries and downloads are NOT committed to git.
  Ignored: sidecars/alicevision/windows-x64/
  Ignored: sidecars/alicevision/downloads/
Tracked: this README, LICENSE.MPL-2.0, scripts/alicevision_manifest.json

Staging (manual / agent)
------------------------
1. Download the ZIP into sidecars/alicevision/downloads/
2. Verify SHA256 against the published GitHub asset digest
3. Extract into sidecars/alicevision/windows-x64/ and flatten so bin/ is
   directly under windows-x64/ (remove the nested aliceVision/ wrapper)
4. See scripts/alicevision_manifest.json for the recorded source of truth

Runtime requirements
--------------------
- Microsoft Visual C++ Redistributable (x64) — REQUIRED for the EXEs to load.
  Without it, processes may exit with STATUS_DLL_INIT_FAILED (0xC0000142).
- ALICEVISION_ROOT must point at sidecars/alicevision/windows-x64 (absolute
  path at process start) so embedded OCIO config under share/ is found.
- CUDA / NVIDIA GPU drivers — OPTIONAL. Needed only for GPU-accelerated
  depth-map nodes (e.g. depthMapEstimation). CPU paths work without CUDA.

Smoke check (example)
---------------------
  set ALICEVISION_ROOT=<repo>\sidecars\alicevision\windows-x64
  sidecars\alicevision\windows-x64\bin\aliceVision_featureExtraction.exe --version
  (prints usage / help; confirms the binary loads)

macOS arm64
-----------
No prebuilt macOS/darwin/arm64 assets on AliceVision releases through v3.3.0.
Status: build-from-source (do not auto-download). See manifest macos-arm64.
