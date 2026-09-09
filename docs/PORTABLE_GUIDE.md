# Portable bootstrap guide (Windows + Linux/WSL2)

Platforms: **Windows native** and **Linux/WSL2** only. **macOS is unsupported**.

## Distribution policy

- **GitHub releases = changelog only.** Бинарные паки на GitHub **не** публикуются.
- Паки собираются локально (`scripts/build_portable.ps1`) и раздаются **внутренним офлайн-каналом** (облачный диск оператора).
- Локально держать ровно два целых ZIP: `portable/MuraveiVision_PRO_Mini.zip` и `portable/MuraveiVision_PRO_FullKit.zip`.

## Goal

Unpack ZIP → `Запустить.bat` → first-run **self-bootstrap** → UI at `http://127.0.0.1:8000`. Логи → `logs/` (или `MURAVEI_LOG_DIR`).

Scripts: `bootstrap_portable.ps1` / `.sh`, `portable_manifest.json`, `setup_env.ps1`, `smoke_portable.ps1`.

## Contents table (detect out-of-box contract)

| | **Mini** (~3.5–4.5 GB, warn &gt;4.5, reject &gt;5) | **FullKit** (~7.5–9 GB, warn &gt;9.5, reject &gt;10) |
|--|--|--|
| Offline stack | tactical YOLO26 (ladder **l-ft &gt; m-ft &gt; s-ft &gt; n-ft &gt; n**) + **SAHI default ON** + **sam3.pt** exactly once | same weights policy + larger tactical weights when present in `assets/models` |
| Runtime | CPU torch + onnxruntime-directml | CUDA torch cu128 (+ CPU fallback) |
| 3D | — | COLMAP + gsplat + AliceVision (when staged) |
| Ollama | **НЕ в комплекте** | **НЕ в комплекте** |
| KIT marker | pack-root `KIT` = `mini` | `KIT` = `full` |
| Badge | `Сборка: Mini · класс: … (tier N)` | `Сборка: Full · класс: … (tier N)` |

**Mini vs Full difference = 3D + CUDA + model size ONLY.** Both are full offline detect/seg stacks (air-gap: zero downloads at first Scan / Segmentation).

### Ollama (system-optional)

Для AI-анализа поставьте Ollama **отдельно**. Air-gap: привезите installer + blob модели в `OLLAMA_MODELS` вручную. Runtime discovery ladder (v3.2) без изменений: `MURAVEI_OLLAMA_URL` → loopback → WSL gateway → saved endpoint. Absent → спокойный серый «Ollama отключена».

### SAHI / CPU segmentation honesty

- «Сканировать»: SAHI default **ON** (toggle persists in settings / config).
- «Сегментация» на CPU: one-time RU ETA «SAM3 на CPU: ~минуты на кадр» + «больше не показывать» → `config/local/ui_flags.json`.
- DirectML ONNX: first accelerated run may export into `config/local/onnx_cache` (CPU `.pt` path never waits).

### Tiers

See `config/hardware_tiers.json` and banner mismatch messages (inform, never block).

## Zero-hardcode (Z1)

Paths repo-relative or `MURAVEI_*`. URLs+sha256 only in `scripts/portable_manifest.json`. Detect weights: **copy-only** at build (never download COCO s/m/l).

## Field checklist

1. Распаковать Mini/Full в чистую папку.
2. Опционально: `wheels/` + `sidecars/` рядом (Full).
3. `Запустить.bat`.
4. «Сканировать» / «Сегментация» работают offline сразу.
5. VLM: поставьте Ollama отдельно при необходимости.

## Smoke

`scripts/smoke_portable.ps1` (Mini CI-required: pack layout + YOLO infer + SAM3 load); `-Full` только локально → `CI: Mini OK / Local: Full OK|skipped`.

Smoke sample: `assets/smoke_sample/frame_person_car.jpg` (synthetic CC0 — see `LICENSE.txt`).

## Offline completeness inventory (что внутри и зачем)

| Component | Mini | FullKit | Mandatory |
|--|--|--|--|
| python 3.12 embeddable | yes | yes | YES |
| torch (cpu) | yes | yes (cpu-flavor) / cuda-flavor when `+cu128` wheels pre-seeded | YES |
| onnx + onnxslim | yes | yes | YES |
| onnxruntime-directml (gpu for cuda-flavor) | yes | yes | YES |
| ultralytics + SAM3 code + sahi | yes | yes | YES |
| fastapi / uvicorn / pydantic / opencv-headless / numpy / pillow | yes | yes | YES |
| yolo26n-ft.pt (+ yolo26n.pt), ladder l-ft>m-ft>s-ft>n-ft>n | yes | yes | YES |
| sam3.pt exactly one | yes | yes | YES |
| **ffmpeg + ffprobe pack-local** (`assets/ffmpeg/`) | yes | yes | YES |
| COLMAP + AliceVision sidecars | — | yes | YES (Full) |
| backend/ + dist/ + assets/smoke_sample/ | yes | yes | YES |
| KIT + VERSION + Запустить.bat | yes | yes | YES |
| FORBIDDEN: ollama/, node_modules, runs/detect >50 MB, sam dups, archive media, .git, *.part/*.tmp | assert | assert | assert |

### Air-gap runtime

- Pack **does not** call the network on start / Scan / Segmentation.
- Ultralytics AutoUpdate disabled: `YOLO_AUTOINSTALL=0` + `ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS=1` + no-op wrapper (`backend/services/ultralytics_airgap.py`).
- Dist-name note: Ultralytics checks metadata name `onnxruntime`, while Mini/CPU ships **`onnxruntime-directml`** (import name still `onnxruntime`). Pins for `onnx`/`onnxslim` + air-gap guard close the AutoUpdate hole.
- ffmpeg/ffprobe resolve order: `MURAVEI_FFMPEG_DIR` → `assets/ffmpeg` → `sidecars/ffmpeg` → PATH (PATH = degrade only).
- ffmpeg redistributable: GPL/LGPL essentials (see `scripts/portable_manifest.json` → `ffmpeg_windows_essentials`).
- ONNX export cache: `config/local/onnx_cache` only (never beside pack `.pt`).
- Smoke poison grep (split): uvicorn/stderr fails on AutoUpdate/pip; bootstrap only on narrow patterns (offline `--no-index` heal allowed).

Size gates: Mini warn >4.5 GB / reject >5 GB; FullKit warn >9.5 GB / reject >10 GB.
