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
