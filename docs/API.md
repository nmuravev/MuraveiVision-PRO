# API Reference

Базовый origin: `http://127.0.0.1:8000`. С фронта — относительные пути `/api/...`.  
Большинство маршрутов требуют `Authorization: Bearer <JWT>` после `POST /api/auth/login`.

## Auth — `/api/auth`

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/login` | PIN → JWT |
| GET | `/me` | текущая сессия |
| GET | `/peek-pin/{role}` | инженер/мастер, UI скрывает |
| POST | `/change-pin` | смена PIN по роли |

## Media — `/api/media`

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/tree` | дерево `archive/` |
| GET | `/stream` | HTTP byte-range streaming (`206`, `Content-Range`) |
| GET | `/filmstrip` | миниатюры таймлайна |
| POST | `/upload` | загрузка в архив |
| POST | `/trash` | в корзину |
| GET | `/trash` | список корзины |
| POST | `/restore` | восстановление |
| DELETE | `/delete` | удаление |
| POST | `/trash/purge` | очистка |
| DELETE | `/trash/permanent` | безвозвратно |

## Detect — `/api/detect`, `/ws/detect/{viewer_id}`

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/detect` | один кадр (base64) |
| GET | `/api/detect/status` | mode, model, device, latency |
| WS | `/ws/detect/{viewer_id}` | поток кадров ↔ детекции |

**Поля запроса (REST body и WS message):**
`image_base64`/`image`, `confidence` (0.05–0.99, default 0.5), `frame_idx`, `time_sec`,
`use_sahi` (bool, optional — включает SAHI-нарезку кадра для поиска мелких объектов на
высоких разрешениях БПЛА; по умолчанию берётся из системной настройки `use_sahi_default`),
`slice_height` (128–2048, default 512), `slice_width` (128–2048, default 512),
`overlap_ratio` (0.0–0.5, default 0.2). Фронтенд не отправляет `use_sahi` — режим
определяется backend-настройкой. Ответ SAHI-пути идентичен быстрому пути + поле
`"sahi": true`. Выходной формат объектов не меняется.

### Response Validator (defense-in-depth)

Валидатор фильтрует детекции перед попаданием в response-конверт (общий хвост
`_finalize_sync` — работает и для быстрого YOLO, и для SAHI). Включён по умолчанию.

Проверки каждой детекции:
- `bbox.x1/y1/x2/y2` в диапазоне `[0, 1]`; `x1 < x2` и `y1 < y2` (дегенеративные отбрасываются)
- площадь bbox в `[0.0001, 0.9]` (нормализованная)
- `confidence` в `[0.01, 1.0]`
- `class_id` присутствует во включённых ID каталога (`get_class_catalog`, `enabled=True`)

Отброшенные детекции пишутся в `logs/validator_rejections.jsonl` — по одной JSON-строке
на запись: `{ts, detection, reasons}`. Формат JSONL (safe append, без read-modify-write).

Настройки (SQLite, `settings`): `validator_enabled` (bool, default `1`),
`validator_min_bbox_area` (float, default `0.0001`),
`validator_max_bbox_area` (float, default `0.9`),
`validator_min_confidence` (float, default `0.01`).

Graceful degradation: при любой ошибке валидатора (или недоступности каталога классов)
все детекции проходят без фильтрации — инференс никогда не падает из-за валидации.
Валидатор — второй эшелон за существующими фильтрами `_boxes_to_objects`
(clamp bbox, area<=0/>=0.55 drop, unmapped drop, per-class confidence).

## System — `/api/system`

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/hardware` | CPU/GPU/VRAM (engineer+) |
| POST | `/selftest` | cuda/model/ollama/disks |
| GET | `/simulate-failure` | активная симуляция |
| POST | `/simulate-failure` | `{type: gpu_oom\|model_missing\|ollama_offline\|clear}` |
| GET | `/detect-config` | текущая конфигурация детекции: SAHI + валидатор (engineer+) |
| PUT | `/detect-config` | `{use_sahi_default, slice_height, slice_width, overlap_ratio, validator_enabled, validator_min_bbox_area, validator_max_bbox_area, validator_min_confidence}` |

`GET/PUT /api/system/detect-config` хранит значения в SQLite (`settings`):
`use_sahi_default` (включает SAHI по умолчанию для всех WS-клиентов),
`sahi_slice_height`, `sahi_slice_width`, `sahi_overlap_ratio`,
`validator_enabled`, `validator_min_bbox_area`, `validator_max_bbox_area`,
`validator_min_confidence`. Значения применяются без перезапуска backend. UI-тумблеры — в панели инженера «Система» → «Конфигурация детекции».

## Batch scan — `/api/scan`

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/scan/start` | `{ video_path, fps_sample?, conf?, save_crops? }` → фоновый скан |
| GET | `/api/scan/status` | текущий job |
| GET | `/api/scan/stream` | SSE прогресс |
| POST | `/api/scan/stop` | остановить |

Детекции пишутся с `origin=batch_scan` в SQLite.  
При наличии sidecar `.SRT`/`.CSV` рядом с видео заполняются `gps_lat` / `gps_lon` / `gps_alt`.

## Geo — `/api/geo`

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/geo/import` | `{ video_path }` → парсинг sidecar, upsert `flight_tracks` |
| GET | `/api/geo/track?video_path=` | точки траектории (предпочтительно для Windows-путей) |
| GET | `/api/geo/track/{video_path}` | то же через path |
| GET | `/api/geo/detections?video_path=` | детекции + GPS |
| GET | `/api/geo/detections/{video_path}` | то же через path |
| POST | `/api/geo/interpolate` | `{ video_path, time_sec }` → одна точка |

Sidecar: тот же stem, что у видео (`.SRT`/`.srt`, затем `.CSV`/`.csv`), только под `archive/`.

Панель **Гео 3D** (`flight3d`) читает track/detections и рисует three.js-сцену (локальная ENU-проекция, без CDN).

## Detections — `/api/detections`

`GET` требует `source_video` (без него возвращает пустой список; `all_videos=true` только для служебных инструментов). CRUD + `POST /commit` (пакет кадра + crops), `GET /{id}/crop`, `GET /{id}/similar`. Массовый soft-delete: `DELETE ?source_video=...&all=true`.

## Train / Export

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/train/start` | `{ epochs }` |
| POST | `/api/train/stop` | остановка |
| GET | `/api/train/status` | состояние |
| GET | `/api/train/stream` | SSE прогресс |
| POST | `/api/export/dataset-zip` | YOLO dataset zip |
| POST | `/api/export/queue-zip` | нарезка In/Out через ffmpeg |
| GET | `/api/export/kml?source_video=` | KML 2.2 (Google Earth), оператор+. Детекции без GPS пропускаются |
| GET | `/api/export/geojson?source_video=` | GeoJSON FeatureCollection, CRS WGS84 |

## AI — `/api/ai`

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/models` | список Ollama |
| POST | `/analyze` | prompt + optional image → текст |
| POST | `/autolabel` | `{ detection_id, model? }` → структурированное предложение класса |

503, если Ollama недоступна.

## Live — `/api/live`

`POST /open`, `DELETE /{viewer_id}`, `GET /status`, `GET /{viewer_id}/frame`, `GET /{viewer_id}/mjpeg`.

`GET /{viewer_id}/status` возвращает `active=false`, если поток завершился, thread умер или не появился первый кадр за open-timeout.

## REC — `/api/rec`

`POST /start`, `POST /stop`, `GET /status`, `GET /list` → `archive/recordings/`.

## Reports / Models / System

- `GET /api/report/html` — автономный HTML-отчёт  
- `GET /api/report/pdf` — технический PDF (схема lon/lat + таблица; карта в KML)  
- `GET /api/models/status`, `POST /api/models/import`, `GET /api/models/import/stream`  
- `GET /api/system/hardware`, `POST /api/system/selftest`, `POST /api/system/simulate-failure`  
- `GET /api/health` — liveness + YOLO/DB

## Classes — `/api/classes`

Каталог 238 + CRUD overrides (`name_ru`, aliases, enabled, `in_prompt`, `confidence_threshold`). Индивидуальный порог применяется в YOLO после общего порога.

## Active learning — `/api/active-learning`

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `?status=pending&source_video=` | очередь операторской проверки |
| POST | `/collect` | собрать low-confidence детекции текущего видео |
| POST | `/{sample_id}/decision` | принять класс или отклонить как false positive |

Принятый образец помечается операторской правкой и остаётся в train dataset; отклонённый становится soft-deleted.

## Recon — `/api/recon`

`POST /start`, `POST /stop`, `GET /status`, `GET /stream`, `GET /manifest`, `PATCH /manifest/{job_id}`, `GET /poses`, `GET /asset/{job_id}/{name}`. `poses` отдаёт ближайшую COLMAP-позу и intrinsics для 2D→3D луча; UI использует Gaussian splat pick с fallback на sparse cloud.

## Network — `/api/network`

Репликация целей между машинами. Инстанс `mode=server` — хаб (принимает JWT-запросы). `mode=client` — фоновый worker (`backend/services/network_sync.py`, тик 30 с): heartbeat, push локальных `direction=out` с `synced_at IS NULL`, pull `GET /targets?since=`, upsert как `direction=in`. Worker стартует вместе с backend всегда; тик no-op, если режим не `client`. Хаб недоступен — UI живой, в статусе `hub_reachable=false`.

Клиент логинится на хаб `POST /api/auth/login` с сохранённым `hub_pin` (PIN роли на хабе, обычно operator).

| Метод | Путь | Роль | Описание |
|-------|------|------|----------|
| GET | `/config` | operator+ | `mode`, `server_ip`, `port`, `base_name`, `base_id`, `has_hub_pin`. Значение PIN **не** возвращается |
| POST | `/config` | engineer+ | Тело: `mode`, `server_ip`, `port`, `base_name`; опционально `hub_pin` (write-only: пустая строка / отсутствие поля **не** затирает сохранённый PIN) |
| GET | `/status` | operator+ | `mode`, `base_id`, `last_sync_ts`, `last_error`, `hub_reachable`, `worker_alive` |
| GET | `/bases` | operator+ | реестр heartbeat |
| POST | `/heartbeat` | operator+ | `{base_id, base_name, ip}` |
| GET | `/targets` | operator+ | активные цели (перед выдачей TTL-purge 24 ч). Query `?since=<epoch>` — только строки с `created_at > since` |
| POST | `/targets` | operator+ | одна строка `direction=out`. Локального зеркала `in` **нет**. Опциональный `id` (UUID) сохраняется. Входящие цели создаёт только worker через upsert (newer-wins по `created_at`) |
| GET | `/messages` | operator+ | чат |
| POST | `/messages` | operator+ | одна строка `direction=out` (без локального зеркала `in`) |

Цели несут GPS и `source_video`. `crop_path` — путь к файлу, байты кропа по сети не гоняются (на другой машине файл может отсутствовать). Upsert: `ON CONFLICT(id)` обновляет только если входящий `created_at` строго больше.

## Support

`POST /api/support/diagnostic-zip` — железо + логи без PIN.
