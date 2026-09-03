# 3D Reconstruction (COLMAP + gsplat)

Visual-only photogrammetry for archive MP4 **without GPS**. Designed for EW/jammed environments where SRT telemetry is unavailable.

## Requirements

| Component | Where |
|-----------|--------|
| Python 3.12.10 | `muravei_env\Scripts\python.exe` only |
| COLMAP | Sidecar `sidecars/colmap` — auto-detect или `COLMAP_ROOT` |
| gsplat (train) | Prebuilt wheel on build machine + NVIDIA CUDA |
| ffmpeg/ffprobe | `assets/ffmpeg.exe` or PATH |

## Quick start

1. Stage COLMAP sidecar (once):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stage_colmap_sidecar.ps1
$env:COLMAP_ROOT = "D:\LLM\MuraveiVision-PRO\sidecars\colmap"
Test-Path "$env:COLMAP_ROOT\colmap.exe"   # True, or COLMAP.bat
& "$env:COLMAP_ROOT\colmap.exe" -h         # quick CLI check (or COLMAP.bat help)
```

2. Start backend (sets `COLMAP_ROOT=sidecars\colmap` automatically):

```powershell
npm run backend
```

Manual override if needed:

```powershell
$env:COLMAP_ROOT = "D:\LLM\MuraveiVision-PRO\sidecars\colmap"
npm run backend
```

3. In UI: open MP4 → **Flight3D** → **Построить 3D** (segment ≤120 s from playhead).

4. After `colmap_done`: toggle **Сцена**, optional **Масштаб** (2 clicks + metres).

5. **Inspector** → **Показать в 3D** on a detection → raycast marker (or «Пересечение не найдено»).

## API

| Method | Path |
|--------|------|
| POST | `/api/recon/start` `{ video_path, t_start?, t_end?, fps_sample }` |
| GET | `/api/recon/status` |
| GET | `/api/recon/stream` (SSE, Authorization header) |
| GET | `/api/recon/manifest?video_path=` |
| PATCH | `/api/recon/manifest/{job_id}` scale / horizon |
| GET | `/api/recon/poses?video_path=&time_sec=` |
| GET | `/api/recon/asset/{job_id}/{name}` |

## Artifacts

```
archive/recon/{job_id}/
├── frames/
├── colmap/sparse/0/
├── camera_poses.json    # R, t, intrinsics, image_size per frame
├── sparse_points.json   # COLMAP point cloud preview
└── manifest.json
```

## Raycast math

- Ray from **drone intrinsics** `(u,v)` pixels — not Three.js NDC.
- `dir_world = R^T @ normalize([(u-cx)/fx, (v-cy)/fy, 1])`
- Intersection: sparse point cloud fallback; splat depth-pick when `.splat`/`.ply` artifact exists.
- Flight3D «Сцена»: `preview.ply` / sparse JSON → `THREE.Points`; `model.ply` / `.splat` → `@mkkellogg/gaussian-splats-3d` DropInViewer.
- `scale_direction` in manifest → local azimuth (North alignment).

## Smoke test

```powershell
npm run smoke:recon
```

## gsplat train (optional)

### Full 3DGS on Windows (VS Build Tools + CUDA 12.8)

PyPI `gsplat` is **JIT-only** (no `csrc`). First CUDA call compiles kernels. On this stack (torch 2.11+cu128, RTX 50xx / sm_120):

1. **MSVC 14.44** via VS 2026 Build Tools (path `...\Visual Studio\18\BuildTools`, not `...\2026\...`):
   ```bat
   call "...\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" -vcvars_ver=14.44
   ```
   MSVC **19.51** is rejected by CUDA 12.8 unless `-allow-unsupported-compiler`.
2. Set `CUDA_HOME` to Toolkit **12.8**, put its `nvcc` first on `PATH`.
3. Put **system** `Python312\Include` on `INCLUDE` (venv often has empty `Include/` — do **not** set `PYTHONHOME` to `muravei_env`).
4. After `pip install gsplat`, apply Windows JIT patch:
   ```powershell
   .\muravei_env\Scripts\python.exe scripts\patch_gsplat_windows_jit.py
   ```
   (MSVC cannot take GCC `-Wno-attributes`; need `WIN32_LEAN_AND_MEAN` / `-Usmall` vs `#define small` in Windows SDK.)
5. One-shot train wrapper (discovers ready jobs unless `-JobId`):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\run_gsplat_train_windows.ps1 -Force -MaxSteps 30000
   ```

Expect `model.ply` **≫ 1 MB** and `gsplat_meta.json` with `"gsplat": true`. Tiny ply (~KB) with `"gsplat": true` means train ran but COLMAP gave almost no Gaussians (weak scene).

### Install / stage

1. Install wheel into `muravei_env`:

```powershell
.\muravei_env\Scripts\pip.exe install --no-cache-dir gsplat
# Prefer a prebuilt CUDA wheel matching torch when available.
# Full 3DGS on Windows: see section above (MSVC 14.44 + patch + CUDA 12.8).
```

2. Stage trainer examples (once on build machine):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stage_gsplat_examples.ps1
# → sidecars/gsplat_examples/simple_trainer.py (+ datasets/)
```

Without `simple_trainer.py`, `gsplat_train_job.py` exports only `preview.ply` (colored COLMAP points).

3. Diagnose + batch train / bootstrap:

```powershell
$env:PYTHONPATH = "backend"
.\muravei_env\Scripts\python.exe backend\scripts\diagnose_recon_scenes.py
.\muravei_env\Scripts\python.exe backend\scripts\batch_gsplat_train.py --job-id <id>
# If CUDA JIT / MSVC unavailable, bootstrap Gaussian PLY from COLMAP points:
.\muravei_env\Scripts\python.exe backend\scripts\batch_gsplat_train.py --job-id <id> --bootstrap-only
```

Env knobs: `GSPLAT_MAX_STEPS` (default 7000 for batch; pipeline default 500), `GSPLAT_TIMEOUT` (default 3600).
`gsplat_train_job.py` passes `--disable_video` so mid-eval trajectory render does not abort train on tiny camera sets.

### Artifact semantics (Flight3D «Сцена»)

| File | UI |
|------|-----|
| `model.ply` | Gaussian splat (DropInViewer) — photorealistic after full train; bootstrap = COLMAP→Gaussians |
| `preview.ply` | Colored point cloud (`THREE.Points`) — **not** photorealistic |
| sparse only | Blue/cyan point cloud from `sparse_points.json` |

When `manifest.artifact` is set (`model.ply` / `preview.ply`), Flight3D shows splat-ready status; raycast prefers sparse cloud until splat depth-pick is wired (C.5).
