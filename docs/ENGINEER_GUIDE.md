# Руководство инженера

Установка, настройка, модели, сеть, диагностика и обслуживание. PIN инженера — `0000000` (сменить после первого развёртывания). Подробности развёртывания — [DEPLOYMENT.md](DEPLOYMENT.md), конфигурации — [CONFIGURATION.md](CONFIGURATION.md), тестов — [TESTING.md](TESTING.md).

## Установка

См. [DEPLOYMENT.md](DEPLOYMENT.md). Кратко:
```powershell
.\muravei_env\Scripts\pip.exe install --no-cache-dir -r backend\requirements.txt
.\muravei_env\Scripts\pip.exe install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu128
npm install
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
- После правки каталога вызвать `validator.refresh_catalog()` (или перезапустить backend) — иначе валидатор отбрасывает новые ID.

## Сеть баз

SYSTEM → Сеть (`mode` off / server / client):

- **server** — этот инстанс хаб (остальные клиенты бьют в его `server_ip`:`port`).
- **client** — фоновый worker каждые ~30 с: login JWT по `hub_pin` (PIN оператора хаба), heartbeat, push несинхронизированных исходящих, pull `GET /api/network/targets?since=`.
- PIN хаба в UI write-only (пустое поле при сохранении не стирает уже записанный).
- Цели несут `source_video` и GPS. TTL 24 ч. Входящие появляются как `direction=in` (не локальное зеркало).
- Статус: `GET /api/network/status` — `hub_reachable`, `last_sync_ts`, `last_error`, `worker_alive`.

Один backend не доказывает репликацию. Ручной тест — **две копии папки** (у каждой свой `muravei.db`):

```
xcopy D:\LLM\MuraveiVision-PRO D:\LLM\MuraveiVision-PRO-Base2 /E /I
```

```
# Terminal 1 — хаб (этот репозиторий)
.\muravei_env\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000

# Terminal 2 — клиент (копия). Не npm run backend: там порт 8000 зашит.
cd D:\LLM\MuraveiVision-PRO-Base2
.\muravei_env\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8001
```

Открыть UI с origin каждого backend (`http://127.0.0.1:8000` и `:8001`, раздача `dist/`), не два Vite-прокси на один API.

1. Base-1: SYSTEM → Сеть → `mode=server`.
2. Base-2: `mode=client`, `server_ip=127.0.0.1`, `port=8000`, PIN хаба = PIN оператора Base-1 (заводской `1234567`, если не меняли).
3. На Base-1 отправить цель. На Base-2 в «Входящие» через ~30 с та же `id`, GPS, `source_video`, `direction=in`.
4. Остановить Base-1: Base-2 UI живой, статус `hub_reachable=false`.

## Диагностика

- `GET /api/detect/status` — mode, model, device, last ms, queue.
- `GET /api/system/hardware` — CPU/GPU/VRAM (pynvml).
- `POST /api/system/selftest` — cuda/model/ollama/disks.
- `POST /api/system/simulate-failure` — `{gpu_oom|model_missing|ollama_offline|clear}` для тестов.
- `DebugPanel` во фронте — логи UI + статус YOLO.
- Логи: `logs/runtime.log`, `logs/ai.log`, `logs/train.log`, `logs/validator_rejections.jsonl`, `logs/sahi_test.json`.
- Support: diagnostic ZIP (Admin/Support).

## Если «ничего не детектит»

1. `GET /api/detect/status`: `mode == ready`? Если `offline` — нет весов; если `error` — упала загрузка.
2. Есть ли `assets/models/yolo26n-ft.pt` (или `yolo26n.pt`)?
3. `confidence` не завышен? (UI порог 0.20 по умолчанию).
4. Ollama offline **не блокирует** YOLO — только AI-вкладку.
5. CUDA OOM → engine сам откатится на CPU (`device_backend=cpu-fallback-oom`, `degraded=true`). При частом — снизить `imgsz`/batch.

## Обслуживание

- **Обновление:** `git pull` → `pip install -r requirements.txt` → `npm install` → `npm run build`. Схема БД мигрируется автоматически (`init_db`, аддитивные `ALTER TABLE`).
- **Portable:** `npm run portable` (Lite) / `npm run portable:full` — [PORTABLE.md](PORTABLE.md). Пекётся embeddable 3.12.10, не хостовый 3.14.
- **Кэш/логи:** `logs/` растут — чистить по необходимости. `MURAVEI_TRASH_PURGE` — автоочистка корзины при старте.
- **Тесты перед коммитом:** `npm run build` → `python -m unittest discover -s tests` (из `backend/`) → `npm run test:field` → `smoke_lbs_ft.py`.

## Типичные ловушки

1. `torch 2.x+cpu` → обучение часами на CPU / `cuda False`. Ставить `--index-url .../cu128`.
2. OOM 8 GB при imgsz=1024 batch=16 → уменьшить imgsz/batch, `empty_cache`.
3. После train UI показывает YOLOE — нужен `force_load` ft (исправлено в engine priority).
4. Circular import в скриптах: сначала `importlib.import_module("main")`.
5. SAHI `pip check` warning (opencv-python non-headless имя) — benign, runtime OK.
