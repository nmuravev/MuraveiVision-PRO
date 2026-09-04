# 3D Reconstruction (COLMAP + gsplat)

Visual-only photogrammetry for archive MP4 **without GPS**. Designed for EW/jammed environments where SRT telemetry is unavailable.

**Paths:** recon `video_path` and media assets resolve through dynamic `archive_root()` / `assert_in_archive` — never bake host absolute paths into manifests or client state. Prefer `archive/...` from the Media API.

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
$env:COLMAP_ROOT = (Resolve-Path ".\sidecars\colmap").Path
Test-Path (Join-Path $env:COLMAP_ROOT "COLMAP.bat")   # or colmap.exe
```

2. Start backend (sets `COLMAP_ROOT=sidecars\colmap` automatically):

```powershell
npm run backend
```

Manual override if needed:

```powershell
$env:COLMAP_ROOT = (Resolve-Path ".\sidecars\colmap").Path
npm run backend
```

3. In UI: open MP4 → **Flight3D** → **Построить 3D** (segment ≤120 s from playhead).

   **Product rule:** «Построить 3D» = **COLMAP sparse only** (`colmap_done`, `manifest.next_action=balanced_for_splat`). Ops modal steps: extracting → colmap → export_poses → load_scene — **no** inline «gsplat train (optional)». Photorealism = UI presets Balanced / Bootstrap / High.

   **Matching (drone video):** frames use **sequential_matcher** (overlap ≈10–15 neighbors, env `COLMAP_SEQUENTIAL_OVERLAP`). Exhaustive matching is **not** the default — it is O(n²) and often crashes GPU (8 GB) mid «Exhaustive feature matching». Opt-in: `COLMAP_MATCHER=exhaustive` only for small sets (≤`COLMAP_EXHAUSTIVE_MAX_IMAGES`, default 80).

   **Frame / size budget (8 GB VRAM):** SfM frame count is capped (`COLMAP_MAX_FRAMES`, default 600); `fps_sample` is clamped to the segment. Longest image side is limited (`COLMAP_MAX_IMAGE_SIZE`, default 1600) at extract + `SiftExtraction.max_image_size`. If GPU matching fails, COLMAP retries **once** with CPU (`SiftMatching.use_gpu=0`) and logs to runtime + Session Trace.

4. After `colmap_done`: toggle **Сцена**, optional **Масштаб** (2 clicks + metres).

## 3D Training via UI

After COLMAP (`colmap_done`), open **Гео 3D → Сцена**. Yellow banner prompts for a train profile (no CLI required):

| Button | Preset | Typical time | Notes |
|--------|--------|--------------|--------|
| Bootstrap | `bootstrap` | ≈30 с | COLMAP→minimal `model.ply` (not photoreal) |
| Balanced | `balanced` (default) | 5–10 мин | gsplat ~7000 steps |
| High Quality | `high` | 15–30 мин | ~30000 steps; **disabled if VRAM &lt; 12 ГБ** |

**UI note:** after COLMAP, «Сцена» may show a light-blue **point cloud** (sparse). That is expected — not a broken canvas. Photorealism requires Balanced/High. Square «cubes» were WebGL point sprites; UI now uses circular discs + CTA banner.

Progress (SSE `/api/recon/train/stream`, poll fallback 3s): steps, loss/PSNR when parsed, VRAM. One train at a time; COLMAP and train mutually disable each other.

Engineer overrides: edit [`config/train_presets.json`](../config/train_presets.json) at **repo root**. Invalid/missing → built-in Balanced + warning in `logs/runtime.log`. UI never exposes raw step inputs.

API: `GET/POST /api/recon/train/presets|status|start|stop|stream`.

## In-panel operations progress modal

Long ops (COLMAP «Построить 3D», train presets, scene load) open a **panel-scoped** progress modal inside Flight3D (not a global app modal):

- Step list from existing SSE/status (`extracting` → COLMAP combined → export → load; or train_start → training → load).
- Live metrics on the current step; collapsible log tail (last **20** lines).
- **Свернуть в фон** → corner chip (spinner + step + %); click restores. Blocking of conflicting controls stays while the op runs even when minimized.
- Success → brief «Готово» (~1.8 s) → auto-dismiss. Error → no auto-dismiss; **Закрыть** / **Повторить**.
- Session Trace: `modal` events for open / minimize / restore / auto-dismiss / error / retry.

## Layout

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

## Job ID format and CLI usage

- Job IDs are **12-character hex** strings from `uuid4().hex[:12]` (never contain spaces at creation).
- Prefer a PowerShell variable so line-wrap copy-paste cannot split the token:

```powershell
$jid = '<12-hex-chars>'
$env:PYTHONPATH = 'backend'
.\muravei_env\Scripts\python.exe backend\scripts\diagnose_recon_scenes.py --job-id $jid --json
```

- Recon CLIs (`diagnose_recon_scenes`, `batch_gsplat_train`) accept `--job-id` with multiple tokens and **join + sanitize** whitespace. `run_gsplat_train_windows.ps1 -JobId` also strips whitespace. Warnings go to stderr if the id was cleaned or is not 12 hex chars.
- If UI shows only a sparse cloud: check `manifest.status` / `artifact`. `colmap_done` + missing `model.ply` means gsplat train has not finished — run the train wrapper with `-JobId $jid`.

## Artifacts

```
archive/recon/{job_id}/
├── frames/
├── colmap/sparse/N/     # COLMAP model(s); best N chosen by max points size
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

**In-app UI train** (`/api/recon/train/*`): Balanced/High call the same gsplat path. Backend discovers `vcvars64` (env `MURAVEI_VCVARS64` / vswhere / Program Files) and launches under MSVC 14.44 when `cl` is not already on PATH. Without MSVC, presets are disabled with a clear reason — use **Bootstrap**. Full stdout is teed to `archive/recon/<job>/train.log`; failures include a short log snippet (not only `exit code N`).

**HUD crop:** when archive HUD exclusion is ON and zones are ready, recon extracts **cropped** frames (static OSD never enters COLMAP). Margins stored in `manifest.hud_crop` (relative %); `camera_poses.json` intrinsics are mapped back to **full-frame** for Inspector raycast.

Expect `model.ply` **≫ 1 MB** and `gsplat_meta.json` with `"gsplat": true`. Tiny ply (~KB) with `"gsplat": true` means train ran but COLMAP gave almost no Gaussians (weak scene).

**Multi-model COLMAP:** if mapper writes several `sparse/N` folders, diagnose / train / bootstrap / in-app recon pick the **largest valid** points cloud (`get_best_sparse_dir`). Trainer staging still copies that model into `gsplat_data/sparse/0/` for gsplat examples.

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
`GSPLAT_INLINE=1` — opt-in short train **inside** «Построить 3D» (`_try_gsplat_train`); **off by default** (honest sparse-only Build3D).
`gsplat_train_job.py` passes `--disable_video` so mid-eval trajectory render does not abort train on tiny camera sets.

### Artifact semantics (Flight3D «Сцена»)

| File | UI |
|------|-----|
| `model.ply` | Gaussian splat (DropInViewer) — photorealistic after full train; bootstrap = COLMAP→Gaussians |
| `preview.ply` | Colored point cloud (`THREE.Points`) — **not** photorealistic |
| sparse only | Blue/cyan point cloud from `sparse_points.json` |

When `manifest.artifact` is set (`model.ply` / `preview.ply`), Flight3D shows splat-ready status; raycast prefers sparse cloud until splat depth-pick is wired (C.5).
