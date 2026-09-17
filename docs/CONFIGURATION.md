# Конфигурация

Все настройки делятся на три слоя: **SQLite `settings`** (runtime, без перезапуска), **модульные константы** (фиксированная политика инференса), **переменные окружения** (deployment/process).

## SQLite `settings` (key/value, таблица `settings`)

Чтение/запись: [backend/services/db.py](../backend/services/db.py) `get_setting(key, default)` / `set_setting(key, value)`. Bool хранится как `"0"`/`"1"`.

| Ключ | Тип | Default | Назначение |
|------|-----|---------|-----------|
| `jwt_secret` | str | auto | секрет JWT |
| `use_sahi_default` | bool | `0` | SAHI по умолчанию для всех WS-клиентов |
| `sahi_slice_height` | int | `512` | высота слайса SAHI |
| `sahi_slice_width` | int | `512` | ширина слайса SAHI |
| `sahi_overlap_ratio` | float | `0.2` | перекрытие слайсов |
| `validator_enabled` | bool | `1` | включён ли Response Validator |
| `validator_min_bbox_area` | float | `0.0001` | мин. площадь bbox (норм.) |
| `validator_max_bbox_area` | float | `0.9` | макс. площадь bbox |
| `validator_min_confidence` | float | `0.01` | мин. confidence |

Установка: `PUT /api/system/detect-config` (SAHI, engineer+) — см. [API.md](API.md). Валидатор/`jwt_secret` — напрямую через `set_setting`.

## Модульные константы YOLO

[backend/services/yolo_engine.py](../backend/services/yolo_engine.py):

| Константа | Значение | Описание |
|-----------|----------|----------|
| `IMGSZ` | `1024` | базовый размер инференса (адаптивно 640/800/1024 по tier) |
| `DEFAULT_CONF` | `0.25` | порог по умолчанию |
| `MAX_SCENE_AREA` | `0.55` | отсев сцен-классов по площади |
| `QUEUE_MAX` | `4` | очередь инференса |
| `NMS_IOU` | `0.45` | IoU для NMS |
| `TILE_OVERLAP` | `0.18` | перекрытие тайлов fallback |
| `COCO_FALLBACK_CONF` | `0.35` | порог COCO-fallback |
| `_STRICT_CONF` | `0.55` | строгий порог (мины/ловушки) |
| `_DRONE_CONF` | `0.35` | порог дронов |
| `_LBS_SOFT_CONF` | `0.12` | мягкий порог LBS-фортификаций |
| `CLIP_MIN_BYTES` | 200 MiB | мин. размер CLIP-энкодера для YOLOE |

Политики-списки: `_COCO_DROP` (COCO-мусор), `_STRICT_TOKENS`, `_LBS_SOFT_TOKENS`, `_BOX_COLORS`.

## SAHI

[backend/services/sahi_yolo_engine.py](../backend/services/sahi_yolo_engine.py), [backend/api/detect.py](../backend/api/detect.py):
- Слайс по умолчанию: `512×512`, overlap `0.2`.
- Диапазоны запроса: `slice_height/width` 128–2048, `overlap_ratio` 0.0–0.5.
- Системный default: **выключено** (`use_sahi_default=0`).
- Переиспользует загруженную модель YOLO (без дубля VRAM).

## Response Validator

[backend/services/response_validator.py](../backend/services/response_validator.py):
- Включён по умолчанию.
- Площадь bbox: `[0.0001, 0.9]`. Confidence: `[0.01, 1.0]`. bbox в `[0,1]` + `x1<x2`, `y1<y2`.
- Лог отбросов: `logs/validator_rejections.jsonl` (JSONL, safe append).
- Кэш enabled class IDs: TTL 300 с; `refresh_catalog()` сбрасывает сразу. При ошибке `get_class_catalog` после expiry сохраняется предыдущий set (backoff 300 с, чтобы не читать YAML каждый кадр).
- Graceful degradation: при ошибке валидатора/каталога все детекции проходят.

## Сеть (таблица `network_config`, не `settings`)

| Поле | Default | Описание |
|------|---------|----------|
| `mode` | `off` | `off` / `server` / `client` |
| `server_ip` | `127.0.0.1` | |
| `port` | `8000` | |
| `base_name` | `База-1` | |
| `base_id` | UUID v4 | генерируется один раз, в GET `/config` |
| `hub_pin` | — | write-only; клиент логинится им на хаб. GET не отдаёт |
| TTL цели | 24ч | `expires_at` в `network_targets` |

API: `GET/POST /api/network/config`, `GET /api/network/status`. Worker: [ENGINEER_GUIDE.md](ENGINEER_GUIDE.md#сеть-баз).

## Классы

- Каталог: `assets/military_classes.yaml` (238 UI-классов).
- Переопределения: таблица `class_overrides` (`name_ru`, `aliases` JSON, `enabled`, `in_prompt`, `confidence_threshold`).
- Слияние YAML + overrides в runtime: [backend/services/classes.py](../backend/services/classes.py) `get_class_catalog()`.
- API: `GET /api/detections/classes`, `PATCH /api/classes/{id}` (engineer+).

## Переменные окружения

Только deployment/process (не inference):
| Переменная | Где | Назначение |
|-----------|-----|-----------|
| `MURAVEI_TRASH_PURGE` | [backend/main.py](../backend/main.py) | автоочистка корзины при старте |
| `MURAVEI_RELOAD` | [backend/main.py](../backend/main.py) | reload uvicorn |
| `MURAVEI_SMOKE_BASE` | smoke-скрипты | базовый URL для smoke |

`python-dotenv` установлен, но `.env` не используется — все runtime-настройки в SQLite.

## Производительность (ms/VRAM @ 8 ГБ)

[backend/services/perf_budget.py](../backend/services/perf_budget.py) — профилирование на RTX 5060 Laptop (8 ГБ VRAM).

| Операция | Latency | Δ VRAM | Примечание |
|----------|---------|--------|------------|
| YOLO detect (single frame) | 12–25 ms | ~2.5 GB | 640→1024, зависит от tier |
| SAHI (N слайсов, 512×512) | N × 15–30 ms | reuse YOLO | По умолчанию off; для 4K-кадров БПЛА |
| Batch seg (frame_step) | 80–150 ms/f | +1.5 GB | SAM3 ~3.5 GB взаимно исключает detect |
| SAM3 propagate (≤30 кадров) | 40–80 ms/f | in-memory | Не персистит; temp clip |
| SAM3 propagate full-video (chunked) | 40–80 ms/f × N окон | in-memory per window | VRAM guard: empty_cache между окнами; 9-мин клип ≈ 2–4 мин GPU / 6–12 мин CPU |
| Change Detection (ORB) | 200–500 ms/pair | ~500 MB | Зависит от coverage GPS/ORB |
| COLMAP sparse (3000 кадров) | 5–15 мин | 4–6 GB | Sequential matcher на drone video |
| gsplat train (30k steps) | 10–30 мин | 5–7 GB | RTX 5060; requires VS Build Tools + CUDA 12.8 |
| DA3 dense (base) | 30–60 ms/patch | +1 GB | Optional sidecar; soft-fail на CPU |
| AliceVision Mesh | 10–30 мин | 6–8 GB | Optional; требует CUDA |

**Правила VRAM-менеджмента:**

- SAM3 и YOLO-seg **взаимно исключают** VRAM; Detect не выгружается при load SAM3.
- На RTX 5060 (8 ГБ) не держать seg и detect одновременно: выгружайте seg перед live-детекцией.
- gsplat train блокирует «Построить 3D»; один train за раз.
- HQ preset disabled при total VRAM < 12 ГБ (typical 8 ГБ field laptop → Balanced или Bootstrap).
