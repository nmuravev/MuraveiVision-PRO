# Руководство инженера

Установка, настройка, модели, сеть, диагностика и обслуживание. PIN инженера — `0000000` (сменить после первого развёртывания). Подробности развёртывания — [DEPLOYMENT.md](DEPLOYMENT.md), конфигурации — [CONFIGURATION.md](CONFIGURATION.md), тестов — [TESTING.md](TESTING.md).

## Установка

См. [DEPLOYMENT.md](DEPLOYMENT.md) и офлайн-пак [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md). Кратко:
```powershell
# Онлайн (dev):
.\muravei_env\Scripts\pip.exe install --no-cache-dir -r backend\requirements.txt
.\muravei_env\Scripts\pip.exe install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu128
npm install

# Поле без интернета: распаковать muravei_env_pack_win_cpu|cuda.zip → scripts\setup_env.bat
# Сборка пака: .\scripts\make_env_pack.ps1 -TorchFlavor cpu|cuda
# AMD field: docs\SPEC_FIELD_MACBOOK.md
```
Правило: только `muravei_env\Scripts\python.exe` (3.12.10) — [.cursor/rules/muravei-python-env.mdc](../.cursor/rules/muravei-python-env.mdc). Bare `python`/`pip` использовать нельзя (PATH → 3.14).

## Запуск

| Сценарий | Команда |
|----------|---------|
| Dev | `npm run backend` + `npm run dev` |
| API только | `start-backend.bat` |
| Desktop | `npm run desktop` |
| Поле | `Запустить.bat` |

Порт API: 8000.

## Настройка (SQLite, без перезапуска)

`GET/POST /api/network/config`, `PUT /api/system/detect-config`, `set_setting` напрямую. Ключи — в [CONFIGURATION.md](CONFIGURATION.md):
- SAHI: `use_sahi_default`, `sahi_slice_height/width`, `sahi_overlap_ratio`.
- Валидатор: `validator_enabled`, `validator_min_bbox_area`, `validator_max_bbox_area`, `validator_min_confidence`.
- `jwt_secret` — сгенерировать при первом развёртывании.

## Модели

- Веса: `runs/detect/train/weights/*.pt` или `assets/models/*.pt`. Приоритет: `yolo26n-ft.pt` > `yolo26n.pt` > `yoloe-*`.
- Нет весов → `mode=offline` (пустые детекции, не ошибка).
- `force_load(weights)` — хард-свитч после promote finetune.
- Каталог классов: `assets/military_classes.yaml` (238), переопределения в `class_overrides` (`PATCH /api/classes/{id}`).
- После правки каталога вызвать `validator.refresh_catalog()` (PUT/DELETE override уже вызывают). Иначе кэш enabled IDs живёт до TTL 300 с.

## Seg-модели

Отдельный пайплайн (`segmentation_engine.py`), **не** base для `yolo26n-ft` и не грузится в `yolo_engine`.

- Файлы: `assets/models/yolo26n-seg.pt` или `yolo26s-seg.pt` (whitelist). YOLOE-seg / detect `.pt` отклоняются.
- Система → «Сегментация (архив)»: выбрать вес → **Загрузить** / **Выгрузить**. API: `POST /api/seg/load` `{weight}`, `POST /api/seg/unload`. JWT operator+ (engineer `0000000` и master тоже).
- Infer (`POST /api/seg/infer`) требует `loaded=true`. Модель остаётся в VRAM до unload или переключения Viewer SEG→Детекция.
- На 8 ГБ не держать seg и detect одновременно. Смена ролика в SEG-режиме unload не вызывает.
- **SAM3 (P3.13.3a):** `assets/models/sam3.pt` (офлайн). Viewer: «Загрузить SAM3» / «Точка» / «SAM из детекции» / «Пропагировать». API: `/api/seg/sam3/{status,load,unload,infer,propagate}`. Загрузка SAM3 выгружает YOLO-seg и наоборот. Batch seg выгружает SAM3 (toast), без auto-reload. Propagate: temp clip ≤30 frames; `persist` → `seg_masks` only.

## Импорт модели с USB

Air-gap: Система → панель «Импорт с USB» (engineer, PIN `0000000`).

1. Вставить флешку с `.pt` (nc 12 или 238) и/или словарём `military_classes.yaml` (`names:` dict или список строк).
2. **Сканировать USB** — `GET /api/models/usb-scan` (только removable; не сеть).
3. **Предпросмотр** — dry-run, файл не копируется.
4. **Да, импортировать** — текущий файл → `*.backup`, копия в `assets/models/yolo26n-ft.pt` (detect) или `military_classes.yaml`.
5. `.pt`: `YoloEngine.force_load()` (VRAM `empty_cache`, без перезапуска). YAML: `invalidate_class_cache()` + `validator.refresh_catalog()`.

Путь источника обязан быть на съёмном корне (иначе 403). Загрузка `.pt` через браузер (`POST /api/models/import`) по-прежнему работает.

## Сеть баз

SYSTEM → Сеть (`mode` off / server / client):

- **server** — этот инстанс хаб (остальные клиенты бьют в его `server_ip`:`port`).
- **client** — фоновый worker каждые ~**15 с**: login JWT по `hub_pin`, heartbeat (LAN IPv4), push/pull targets, push/pull **messages**.
- PIN хаба в UI write-only (пустое поле при сохранении не стирает уже записанный).
- Цели несут `source_video` и GPS. TTL 24 ч. Чат — отдельное окно ViewId `chat`. См. [NETWORK_REPLICATION.md](NETWORK_REPLICATION.md).
- Статус: `GET /api/network/status` — `hub_reachable`, `advertise_ip`, `last_sync_ts`, `last_error`, `worker_alive`.

Один backend не доказывает репликацию. Ручной тест — **две копии папки** (у каждой свой `muravei.db`):

```
xcopy .\MuraveiVision-PRO .\MuraveiVision-PRO-Base2 /E /I
```

```
# Terminal 1 — хаб (этот репозиторий)
.\muravei_env\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000

# Terminal 2 — клиент (копия). Не npm run backend: там порт 8000 зашит.
cd ..\MuraveiVision-PRO-Base2
.\muravei_env\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8001
```

Открыть UI с origin каждого backend (`http://127.0.0.1:8000` и `:8001`, раздача `dist/`), не два Vite-прокси на один API.

1. Base-1: SYSTEM → Сеть → `mode=server`.
2. Base-2: `mode=client`, `server_ip=127.0.0.1`, `port=8000`, PIN хаба = PIN оператора Base-1 (заводской `1234567`, если не меняли).
3. На Base-1 отправить цель. На Base-2 в «Входящие» через ~30 с та же `id`, GPS, `source_video`, `direction=in`.
4. Остановить Base-1: Base-2 UI живой, статус `hub_reachable=false`.

Автоматический gate (hub :8000 + Base2 :8001, свои `muravei.db`):

```
.\muravei_env\Scripts\python.exe backend\scripts\dual_network_smoke.py
```

Ожидается 7/7 PASS (bases LAN IP, chat both ways, unread, GPS target, no-dup, targets regression).

## Диагностика

- `GET /api/detect/status` — mode, model, device, last ms, queue.
- `GET /api/system/hardware` — CPU/GPU/VRAM (pynvml).
- `POST /api/system/selftest` — cuda/model/ollama/disks.
- `POST /api/system/simulate-failure` — `{gpu_oom|model_missing|ollama_offline|clear}` для тестов.
- `DebugPanel` во фронте — логи UI + статус YOLO.
- Логи: `logs/runtime.log`, `logs/ai.log`, `logs/train.log`, `logs/validator_rejections.jsonl`, `logs/sahi_test.json`.
- Support: diagnostic ZIP (Admin/Support).

## 3D / gsplat (build machine)

### Build3D vs train presets

- **«Построить 3D»** runs COLMAP → poses → sparse only. Does **not** call inline gsplat unless `GSPLAT_INLINE=1`.
- Photoreal / dense / mesh = Flight3D hierarchy (**Sparse / Dense / Mesh / Splat**) or aliases Bootstrap / Balanced / High. See [ALICEVISION.md](ALICEVISION.md).
- After sparse: `manifest.next_action = "balanced_for_splat"` drives the yellow CTA. Successful Splat (`_patch_artifact` → `model.ply`) **clears** `next_action`; FE also hides the CTA when `classifyArtifact(artifact)==='splat'`.

```powershell
# Rare: re-enable short inline train after COLMAP (not recommended for field UX)
$env:GSPLAT_INLINE = "1"
```

### UI presets (`config/train_presets.json`)

Repo-root JSON controls Flight3D **Сцена** buttons. Canonical hierarchy: `sparse` / `da3_dense_*` / `mesh` / `splat`; aliases `bootstrap` / `balanced` / `high`. Scripts: `colmap_only` | `da3_dense` | `alicevision_mesh` | `gsplat` (legacy `alicevision_mvs` behind `MURAVEI_LEGACY_AV_DENSE=1`). Missing/invalid file → built-in hierarchy.

VRAM gate uses `torch.cuda.get_device_properties(0).total_memory` (no `nvidia-smi`). Dense = DA3 (CUDA + `sidecars/da3`). Mesh requires AliceVision sidecar + CUDA + `alicevision_enabled=1`.

### DA3 Dense sidecar (FullKit optional)

```powershell
# Seed weights (Z1 URLs+sha in scripts/portable_manifest.json) then verify:
.\muravei_env\Scripts\python.exe scripts\fetch_da3_weights.py --variants base,large,metric,giant
.\muravei_env\Scripts\python.exe backend\scripts\verify_da3_weights.py
# NOTICE_CC-BY-NC-4.0.txt must sit next to NC weights (large/giant) before FullKit build.
```

### AliceVision Mesh sidecar (opt-in)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\fetch_alicevision.ps1
$env:ALICEVISION_ROOT = (Resolve-Path ".\sidecars\alicevision\windows-x64").Path
```

VC++ Redistributable x64 required. Depth maps need NVIDIA CUDA (no CPU fallback). Engineer toggle: Система → Конфигурация 3D → `alicevision_enabled`.

### CLI (optional)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stage_gsplat_examples.ps1
$env:PYTHONPATH = "backend"
.\muravei_env\Scripts\python.exe backend\scripts\diagnose_recon_scenes.py
# Full Windows train (MSVC 14.44 + CUDA 12.8 + JIT patch):
powershell -ExecutionPolicy Bypass -File scripts\run_gsplat_train_windows.ps1 -Force -MaxSteps 30000
.\muravei_env\Scripts\python.exe backend\scripts\batch_gsplat_train.py --job-id <id>
# Without MSVC / CUDA JIT: bootstrap COLMAP→model.ply for Flight3D «Сцена»
.\muravei_env\Scripts\python.exe backend\scripts\batch_gsplat_train.py --job-id <id> --bootstrap-only
```

### 3D Reconstruction Prerequisites (Windows full 3DGS)

| Component | Notes |
|-----------|--------|
| VS Build Tools | `...\Visual Studio\18\BuildTools`; use **MSVC 14.44** (`vcvars64 -vcvars_ver=14.44`) |
| CUDA Toolkit | **12.8** matching torch cu128 |
| gsplat | `pip install gsplat` then `scripts\patch_gsplat_windows_jit.py` |
| GPU | NVIDIA CUDA (RTX 50xx: `TORCH_CUDA_ARCH_LIST=12.0`) |

Do **not** set `PYTHONHOME` to `muravei_env`. Details: [RECON_3D.md](RECON_3D.md).

## Если «ничего не детектит»

1. `GET /api/detect/status`: `mode == ready`? Если `offline` — нет весов; если `error` — упала загрузка.
2. Есть ли `assets/models/yolo26n-ft.pt` (или `yolo26n.pt`)?
3. `confidence` не завышен? (UI порог 0.20 по умолчанию).
4. Ollama offline **не блокирует** YOLO — только AI-вкладку.
5. CUDA OOM → engine сам откатится на CPU (`device_backend=cpu-fallback-oom`, `degraded=true`). При частом — снизить `imgsz`/batch.

## Обслуживание

- **Обновление:** `git pull` → `pip install -r requirements.txt` → `npm install` → `npm run build`. Схема БД мигрируется автоматически (`init_db`, аддитивные `ALTER TABLE`).
- **Portable:** `npm run portable` (Lite) / `portable:mini` / `portable:full` — [PORTABLE.md](PORTABLE.md), [PORTABLE_GUIDE.md](PORTABLE_GUIDE.md). Пекётся embeddable 3.12.10. **GitHub releases = changelog only** — ZIP не заливать; паки локально в `portable/` → внутренний офлайн-канал.
- **Кэш:** `portable/stage_*`, `portable/cache`, `portable/fullkit_parts` — мусор после сборки, удалять. `wheels/` / `sidecars/` — KEEP.
- **Логи:** единый дом `logs/` (или `MURAVEI_LOG_DIR`). Runtime/uvicorn/bootstrap пишут туда. Job `train.log` остаётся в `archive/recon/<job>/`.
- **Кэш/логи рост:** чистить `logs/` и stage-кэши по необходимости. `MURAVEI_TRASH_PURGE` — автоочистка корзины при старте.
- **Тесты перед коммитом:** `npm run build` → `python -m unittest discover -s tests` (из `backend/`) → `npm run test:field` → `smoke_lbs_ft.py`.

## Офлайн карты для HTML-отчётов

HTML-отчёты Change Detection могут показывать карту GPS. В поле (air-gap) **не** используется OpenStreetMap CDN: нужны заранее скачанные тайлы. Без тайлов отчёт всё равно открывается (таблицы), на карте — подсказка.

### Куда положить

- Папка XYZ: `assets/map_tiles/{z}/{x}/{y}.png`
- или MBTiles: `assets/map_tiles.mbtiles` (Leaflet XYZ ↔ TMS: `y_tms = (2^z - 1) - y`)

Файлы **не** коммитятся в git (см. `.gitignore`).

### Как скачать (QGIS / MOBAC)

1. QGIS + плагин QuickOSM / Generate XYZ tiles, или **Mobile Atlas Creator (MOBAC)**.
2. Выберите район полёта; zoom **10–16** (баланс детализации и размера).
3. Сохраните MBTiles → скопируйте в `assets/map_tiles.mbtiles`, либо распакуйте в `assets/map_tiles/`.

### Проверка

```powershell
# backend должен быть запущен на :8000
curl http://127.0.0.1:8000/api/map/status
# {"tiles_available": true}

curl -o tile.png http://127.0.0.1:8000/api/map/tiles/14/8500/5200.png
```

Скачанный HTML тянет тайлы с `http://127.0.0.1:8000/api/map/tiles/...` — backend должен быть поднят на этой машине. Leaflet CSS/JS по-прежнему с unpkg (для полностью офлайн UI кэшируйте их отдельно при необходимости).

## Типичные ловушки

1. `torch 2.x+cpu` → обучение часами на CPU / `cuda False`. Ставить `--index-url .../cu128`.
2. OOM 8 GB при imgsz=1024 batch=16 → уменьшить imgsz/batch, `empty_cache`.
3. После train UI показывает YOLOE — нужен `force_load` ft (исправлено в engine priority).
4. Circular import в скриптах: сначала `importlib.import_module("main")`.
5. SAHI `pip check` warning (opencv-python non-headless имя) — benign, runtime OK.
