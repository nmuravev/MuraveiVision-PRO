# Portable ZIP

## Цель

Полевой комплект Windows: распаковал → `Запустить.bat` → UI на `http://127.0.0.1:8000` **без** установки Node/Python на целевой машине.

Скрипт: [`scripts/build_portable.ps1`](../scripts/build_portable.ps1).

**Python:** только embeddable / `muravei_env` **3.12.10**. Host `C:\Python314` и bare `python` запрещены.

## Hardening (v3.1)

- **Unique staging:** каждый запуск пишет в `portable/stage_<Kit>_<yyyyMMdd_HHmmss>/`; в начале чистятся старые `stage_*`, `*.locked_*` и legacy fixed-name dirs. ZIP-имена стабильны (`MuraveiVision_PRO_Mini.zip` и т.д.).
- **Host-pip bake:** зависимости ставятся через host `muravei_env\Scripts\python.exe -m pip --python <staged_python>` — **не** через staged `python -m pip` (ломается AV / пропадает `cacert.pem`).
- **Offline wheels:** предпочтительно `portable/cache/wheels` (`--no-index --find-links`). Один раз на машине сборки:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\cache_portable_wheels.ps1
  # FullKit + cu128 torch (CPU wheels also kept — do not delete either):
  powershell -ExecutionPolicy Bypass -File scripts\cache_portable_wheels.ps1 -WithTorchCu128
  ```
- **Torch by kit profile** ([`scripts/portable_torch_policy.py`](../scripts/portable_torch_policy.py)): **Mini/Lite → CPU only**; **FullKit → CUDA cu128** (or `-TorchFlavor cpu`). Cache may hold both `+cpu` and `+cu*` wheels — build filters find-links by profile (never «first found»). Post-stage assert: Mini `torch.version.cuda is None`; FullKit CUDA `is not None`. Mini ZIP fails if &gt; ~1.2 GB (CUDA leak).
- **CA bundle:** стабильный `portable/cache/cacert.pem` (вне stage site-packages); env `SSL_CERT_FILE` / `PIP_CERT` / …
- **Robocopy fallback:** только если host-pip bake упал, или `MURAVEI_PORTABLE_MIRROR=1`. **Never** set `MURAVEI_PORTABLE_MIRROR=1` for Mini (mirrors host CUDA).
- **Перед сборкой:** остановите host `uvicorn` / portable stage (DLL locks). Если AV держит файлы — перезагрузка ПК, затем повтор.

Все пути в скриптах — относительно корня репо / env (`OLLAMA_MODELS`, `%USERPROFILE%\.ollama`, `-OllamaModelsRoot`). Без абсолютных `D:\…` machine paths.

## Матрица комплектов

| Режим | npm / флаг | Содержимое | ZIP |
|-------|------------|------------|-----|
| **Lite** | `npm run portable` | UI + backend + embed Python + **detect YOLO `.pt`** (без seg/SAM/yoloe) | `MuraveiVision_PRO_Portable.zip` |
| **Mini** | `npm run portable:mini` (`-NoDetectWeights`) | как Lite **без** detect `.pt` / mobileclip; **torch CPU**; target ~540–600 MB | `MuraveiVision_PRO_Mini.zip` |
| **Full** | `npm run portable:full` (`-FullKit -IncludeAliceVision`) | Lite + Ollama runtime + torch **cu128** + **`sidecars/colmap`** + **`sidecars/gsplat_examples`** + **`sidecars/alicevision`** (`-IncludeOllamaModel` for VL blobs) | `MuraveiVision_PRO_FullKit.zip` |

**Не путать:** «Mini без AI» ≠ Lite. Lite уже с YOLO detect. Настоящий лёгкий кит — **Mini** (`-NoDetectWeights`).

**Не входит ни в один ZIP по умолчанию:** `assets/map_tiles` (gitignored offline maps), SAM/seg веса, host `muravei_env` с Python 3.14. Карты при необходимости кладите рядом отдельно.

## Сборка Lite

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1 -FetchEmbeddablePython
# или
npm run portable
```

## Сборка Mini (без detect-весов)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1 -FetchEmbeddablePython -NoDetectWeights
# или
npm run portable:mini
```

## Сборка Full Field Kit

Предусловие: на машине сборки уже есть модель:

```powershell
ollama pull qwen2.5vl:7b
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1 -FetchEmbeddablePython -FullKit -IncludeAliceVision
# или
npm run portable:full
```

Опционально: `-OllamaZipPath`, `-OllamaVersion v0.11.4`, `-OllamaModelsRoot` (папка с `blobs\` + `manifests\`; build-time candidates: `OLLAMA_MODELS`, `%USERPROFILE%\.ollama` / `.ollama\models` — **не** runtime-пути в ZIP), `-SkipNpmBuild`, `-SkipZip`, `-NoAliceVision`.

В FullKit копируется **только** `qwen2.5vl:7b` (~6 GB blobs), не весь локальный store Ollama.
3D: `sidecars/colmap` + `sidecars/gsplat_examples` (если есть в репо; иначе WARNING).
AliceVision Dense/Mesh: `npm run portable:full` передаёт `-IncludeAliceVision` (копирует `sidecars/alicevision/windows-x64` ~2.8 GB extracted; WARNING если bins нет). Без флага FullKit всё равно включает AV, если bins уже staged. `-NoAliceVision` — пропуск. Mini никогда не бандлит AliceVision.

Ожидаемый размер Full ZIP с AliceVision порядка **17–20 GB** (без AV ~12–17 GB).

## Что кладётся (Lite)

- `backend/`, `dist/` (с CSP)
- embeddable `muravei_env` + pip из `backend/requirements.txt`
- detect `.pt` (без `*seg*` / `yoloe*` при копировании)
- `military_classes.yaml`, `Запустить.bat`
- опционально `mobileclip2_b.ts`
- пустые `archive/`, `cache/`, `logs/`, `reports/`

Полевое обновление модели без интернета: Система → **Импорт с USB**. См. [ENGINEER_GUIDE.md](ENGINEER_GUIDE.md#импорт-модели-с-usb).

## Что добавляет Full Kit

- `ollama/ollama.exe` (+ DLL)
- `ollama/models/` — только `qwen2.5vl:7b`
- `torch`+`torchvision` **cu128**
- `sidecars/colmap`, `sidecars/gsplat_examples`
- `sidecars/alicevision` (optional Dense/Mesh; FullKit only when staged)
- `PORTABLE_README.md`
- `Запустить.bat` поднимает `ollama serve` и `COLMAP_ROOT` если sidecar есть

## Железо

- Windows 10/11 **amd64**
- Рекомендуется **NVIDIA** для realtime
- Без GPU: YOLO/Ollama на CPU; Intel Arc/XPU — вне скоупа

## Лаунчер `Запустить.bat`

ASCII + CRLF. Banner читает корневой `VERSION` (`MuraveiVision PRO v%VER%`, missing → `unknown`). Backend: **module mode** (`python -m uvicorn main:app --app-dir backend`), не `python backend\main.py`. Calls `scripts\bootstrap_portable.ps1` (venv audit / offline-first) before start — see [PORTABLE_GUIDE.md](PORTABLE_GUIDE.md). `COLMAP_ROOT=%~dp0sidecars\colmap` выставляется **только если** sidecar присутствует. `ALICEVISION_ROOT=%~dp0sidecars\alicevision\windows-x64` — если есть `aliceVision_*.exe`. `MURAVEI_SESSION_TRACE=1` по умолчанию. Smoke/CI: `MURAVEI_NO_PAUSE=1` `MURAVEI_NO_BROWSER=1`.

## Проверка комплекта

1. Распаковать на чистую машину / другую папку.  
2. `Запустить.bat` (bootstrap сам доустановит неполный env / пересоберёт битый).  
3. Lite: YOLO ready; Mini: detect 503 до USB-import; Full: ollama + COLMAP_ROOT.  
4. Smoke (operator path): `powershell -File scripts\smoke_portable.ps1` (Mini); `-Full` только локально — fails on Traceback/ImportError/circular import, banner≠VERSION, health≠200.  
5. Layout: `.\muravei_env\Scripts\python.exe backend\scripts\smoke_fullkit_layout.py`
