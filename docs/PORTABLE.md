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
  # FullKit + cu128 torch:
  powershell -ExecutionPolicy Bypass -File scripts\cache_portable_wheels.ps1 -WithTorchCu128
  ```
- **CA bundle:** стабильный `portable/cache/cacert.pem` (вне stage site-packages); env `SSL_CERT_FILE` / `PIP_CERT` / …
- **Robocopy fallback:** только если host-pip bake упал, или `MURAVEI_PORTABLE_MIRROR=1`.
- **Перед сборкой:** остановите host `uvicorn` / portable stage (DLL locks). Если AV держит файлы — перезагрузка ПК, затем повтор.

Все пути в скриптах — относительно корня репо / env (`OLLAMA_MODELS`, `%USERPROFILE%\.ollama`, `-OllamaModelsRoot`). Без абсолютных `D:\…` machine paths.

## Матрица комплектов

| Режим | npm / флаг | Содержимое | ZIP |
|-------|------------|------------|-----|
| **Lite** | `npm run portable` | UI + backend + embed Python + **detect YOLO `.pt`** (без seg/SAM/yoloe) | `MuraveiVision_PRO_Portable.zip` |
| **Mini** | `npm run portable:mini` (`-NoDetectWeights`) | как Lite **без** detect `.pt` / mobileclip (YOLO → 503 до USB-import) | `MuraveiVision_PRO_Mini.zip` |
| **Full** | `npm run portable:full` (`-FullKit`) | Lite + Ollama `qwen2.5vl:7b` + torch **cu128** + **`sidecars/colmap`** + **`sidecars/gsplat_examples`** | `MuraveiVision_PRO_FullKit.zip` |

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
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1 -FetchEmbeddablePython -FullKit
# или
npm run portable:full
```

Опционально: `-OllamaZipPath`, `-OllamaVersion v0.11.4`, `-OllamaModelsRoot` (папка с `blobs\` + `manifests\`; build-time candidates: `OLLAMA_MODELS`, `%USERPROFILE%\.ollama` / `.ollama\models` — **не** runtime-пути в ZIP), `-SkipNpmBuild`, `-SkipZip`.

В FullKit копируется **только** `qwen2.5vl:7b` (~6 GB blobs), не весь локальный store Ollama.  
3D: `sidecars/colmap` + `sidecars/gsplat_examples` (если есть в репо; иначе WARNING).

Ожидаемый размер Full ZIP порядка **12–18 GB**.

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
- `PORTABLE_README.md`
- `Запустить.bat` поднимает `ollama serve` и `COLMAP_ROOT` если sidecar есть

## Железо

- Windows 10/11 **amd64**
- Рекомендуется **NVIDIA** для realtime
- Без GPU: YOLO/Ollama на CPU; Intel Arc/XPU — вне скоупа

## Лаунчер `Запустить.bat`

ASCII + CRLF. `COLMAP_ROOT=%~dp0sidecars\colmap` выставляется **только если** sidecar присутствует. `MURAVEI_SESSION_TRACE=1` по умолчанию.

## Проверка комплекта

1. Распаковать на чистую машину / другую папку.  
2. `Запустить.bat`.  
3. Lite: YOLO ready; Mini: detect 503 до USB-import; Full: ollama + COLMAP_ROOT.  
4. Smoke layout:  
   `.\muravei_env\Scripts\python.exe backend\scripts\smoke_fullkit_layout.py`
