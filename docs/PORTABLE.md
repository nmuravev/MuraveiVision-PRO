# Portable ZIP — Матрица комплектов

## Цель

Полевой комплект Windows: распаковал → `Запустить.bat` → UI на `http://127.0.0.1:8000` **без** установки Node/Python на целевой машине.

Скрипт: [`scripts/build_portable.ps1`](../scripts/build_portable.ps1).

**Python:** только embeddable `muravei_env` **3.12.10** (включён в оба пака). Host `C:\Python314` и bare `python` запрещены.

## Готовность к запуску

**Оба пака (Mini и FullKit) включают полный embeddable Python 3.12.10 с всеми зависимостями.**

Система запускается **сразу после распаковки** — никаких дополнительных установок, докачек или настроек не требуется:

```bash
# 1. Распаковать ZIP
unzip MuraveiVision_PRO_Mini.zip -d C:\MuraveiVision

# 2. Запустить — работает сразу!
cd C:\MuraveiVision
Запустить.bat
```

**Что включено в `muravei_env/`:**
- ✅ Python 3.12.10 embeddable
- ✅ FastAPI, uvicorn, pydantic
- ✅ Ultralytics (YOLO26), SAHI, OpenCV
- ✅ ONNX Runtime + DirectML (Mini) / CUDA (FullKit)
- ✅ Pillow, numpy, timm, safetensors
- ✅ Все transitivе зависимости

**Не входит:** Ollama (system-optional), `assets/map_tiles` (ship separately).

## Матрица комплектов

### 1. Mini — Лёгкая сборка

```powershell
npm run portable:mini
# или
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1 -FetchEmbeddablePython -Mini
```

**Назначение:** Полевая работа: обнаружение (YOLO26) + сегментация (SAM3) + SAHI. Минимальный размер, максимальная портативность.

**Включено:**
- ✅ `muravei_env/` — embeddable Python 3.12.10 + все зависимости (готов к запуску)
- ✅ `backend/` — FastAPI бэкенд
- ✅ `dist/` — UI (React + CSP)
- ✅ `assets/models/yolo26*.pt` — tactical модели (copy-only, без скачивания)
- ✅ `assets/models/sam3.pt` — сегментация
- ✅ `assets/ffmpeg/` — ffmpeg + ffprobe
- ✅ `assets/smoke_sample/` — smoke-тесты (CC0)
- ✅ `military_classes.yaml` — словарь классов
- ✅ `VERSION` + `KIT=mini` — метаданные
- ✅ `Запустить.bat` — лаунчер (CRLF)
- ✅ torch **CPU** + DirectML (без GPU)
- ✅ пустые `archive/`, `cache/`, `logs/`, `reports/`

**НЕ включено:**
- ❌ AliceVision (3D reconstruction)
- ❌ DA3 Dense (neural dense reconstruction)
- ❌ COLMAP (structure-from-motion)
- ❌ gsplat_examples (3D Gaussian splatting)
- ❌ Ollama (AI-анализ, system-optional)

**Размер:** ~4.5 GB (warn >4.5 GB, reject >5 GB)

**Железо:** CPU + DirectML OK; без GPU «Сканировать»/«Сегментация» работают (SAM3 на CPU медленный)

---

### 2. FullKit — Полная сборка

```powershell
npm run portable:full
# или
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1 -FetchEmbeddablePython -FullKit -IncludeAliceVision
```

**Назначение:** Полный набор: обнаружение + сегментация + 3D реконструкция (COLMAP + AliceVision + gsplat) + DA3 Dense.

**Включено (всё из Mini +):**
- ✅ torch **CUDA cu128** (NVIDIA GPU)
- ✅ `sidecars/colmap/` — COLMAP (structure-from-motion)
- ✅ `sidecars/gsplat_examples/` — 3D Gaussian splatting
- ✅ `sidecars/alicevision/` — AliceVision Mesh (opt-in через `-IncludeAliceVision`)
- ✅ `sidecars/da3/` — DA3 Dense веса (если есть под `sidecars/da3/`)
  - `da3_base.safetensors`, `da3_large.safetensors`, `da3_metric.safetensors`, `da3_giant.safetensors`
  - `NOTICE_CC-BY-NC-4.0.txt` (обязателен для NC весов)
  - `config_*.json`

**НЕ включено:**
- ❌ Ollama (AI-анализ, system-optional)

**Размер:**
- FullKit без DA3: warn >9.5 GB, reject >10 GB
- FullKit + DA3 (все 4 варианта): warn >18 GB, reject >22 GB

**Железо:** Windows 10/11 **amd64**; **NVIDIA GPU** рекомендуется для realtime CUDA (FullKit)

---

### Сравнительная таблица

| Компонент | Mini | FullKit |
|-----------|------|---------|
| **Python 3.12.10 (muravei_env)** | ✅ | ✅ |
| **Backend + UI** | ✅ | ✅ |
| **YOLO26 модели** | ✅ | ✅ |
| **SAM3** | ✅ | ✅ |
| **FFmpeg** | ✅ | ✅ |
| **torch CPU / DirectML** | ✅ | ❌ |
| **torch CUDA cu128** | ❌ | ✅ |
| **COLMAP** | ❌ | ✅ |
| **gsplat_examples** | ❌ | ✅ |
| **AliceVision** | ❌ | ✅ (opt-in) |
| **DA3 Dense** | ❌ | ✅ (если есть веса) |
| **Ollama** | ❌ | ❌ (system-optional) |
| **Размер ZIP** | ~4.5 GB | ~8–22 GB |
| **KIT** | `mini` | `full` |
| **GPU requirement** | CPU OK | NVIDIA recommended |

## Hardening (v3.1)

- **Unique staging:** каждый запуск пишет в `portable/stage_<Kit>_<yyyyMMdd_HHmmss>/`; в начале чистятся старые `stage_*`, `*.locked_*` и legacy fixed-name dirs. ZIP-имена стабильны (`MuraveiVision_PRO_Mini.zip` и т.д.).
- **Host-pip bake:** зависимости ставятся через host `muravei_env\Scripts\python.exe -m pip --python <staged_python>` — **не** через staged `python -m pip` (ломается AV / пропадает `cacert.pem`).
- **Offline wheels:** предпочтительно `portable/cache/wheels` (`--no-index --find-links`). Один раз на машине сборки:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\cache_portable_wheels.ps1
  # FullKit + cu128 torch (CPU wheels also kept — do not delete either):
  powershell -ExecutionPolicy Bypass -File scripts\cache_portable_wheels.ps1 -WithTorchCu128
  ```
- **Torch by kit profile** ([`scripts/portable_torch_policy.py`](../scripts/portable_torch_policy.py)): **Mini → CPU only** (require explicit `+cpu` wheel tag; unmarked PyPI torch is rejected); **FullKit → CUDA cu128** (or `-TorchFlavor cpu`). Cache may hold both `+cpu` and `+cu*` wheels — build filters find-links by profile (never «first found»). Post-stage assert: Mini `torch.version.cuda is None`; FullKit CUDA `is not None`. **Size bands (OPERATOR-SANCTIONED 2026-09-16):** Mini warn&gt;4.5 / reject&gt;5; FullKit without DA3 warn&gt;9.5 / reject&gt;10; FullKit+DA3 (all four variants including giant) warn&gt;18 / reject&gt;22. Giant stays in FullKit for heterogeneous fleets (grey on VRAM&lt;16 GB). Mini swap `onnxruntime-gpu` → **`onnxruntime-directml`** (`--no-deps` + re-pin `numpy&lt;2`).
- **Embed python path:** portable kits must use `muravei_env\python.exe` (with `python*._pth`). Do **not** copy `python.exe` into `Scripts\` — without `._pth` it resolves to host/system `sys.prefix`. `Запустить.bat` prefers embed root.
- **CA bundle:** стабильный `portable/cache/cacert.pem` (вне stage site-packages); env `SSL_CERT_FILE` / `PIP_CERT` / …
- **Robocopy fallback:** только если host-pip bake упал, или `MURAVEI_PORTABLE_MIRROR=1`. **Never** set `MURAVEI_PORTABLE_MIRROR=1` for Mini (mirrors host CUDA).
- **Перед сборкой:** остановите host `uvicorn` / portable stage (DLL locks). Если AV держит файлы — перезагрузка ПК, затем повтор.

Все пути в скриптах — относительно корня репо / env. Без абсолютных `D:\…` machine paths. Ollama **не** бандлится (system-optional).

## Что кладётся (оба пака)

- `backend/`, `dist/` (с CSP), embeddable `muravei_env` 3.12.10
- `assets/models/yolo26*.pt` (tactical, copy-only) + **exactly one** `sam3.pt`
- pack-root `VERSION` + `KIT` (`mini`|`full`)
- `assets/smoke_sample/` (CC0 synthetic for functional smoke)
- пустые `archive/`, `cache/`, `logs/`, `reports/`; `runs/detect` stub &lt;50 MB
- **нет** `ollama/`

FullKit additionally: torch cu128, `sidecars/colmap`, `gsplat_examples`, AliceVision when staged.

## Железо

- Windows 10/11 **amd64**
- Рекомендуется **NVIDIA** для realtime CUDA (Full)
- Mini: CPU + DirectML; без GPU «Сканировать»/«Сегментация» работают (SAM3 на CPU медленный)

## Лаунчер `Запустить.bat`

ASCII + CRLF. Banner читает корневой `VERSION`. Backend: **module mode**. Bootstrap Z2 перед стартом. `COLMAP_ROOT` / `ALICEVISION_ROOT` только если sidecar есть. Smoke/CI: `MURAVEI_NO_PAUSE=1` `MURAVEI_NO_BROWSER=1`.

## Проверка комплекта

1. Распаковать на чистую машину / другую папку.
2. `Запустить.bat`.
3. Mini/Full: «Сканировать» + «Сегментация» offline сразу; badge `Сборка: Mini|Full · …`.
4. Smoke: `powershell -File scripts\smoke_portable.ps1` (Mini CI); `-Full` локально → `CI: Mini OK / Local: Full OK|skipped`.
5. Layout Full: `.\muravei_env\Scripts\python.exe backend\scripts\smoke_fullkit_layout.py`

