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

## Seg — `/api/seg` (архив)

Отдельный пайплайн от детекции. Веса только `assets/models/yolo26n-seg.pt` или `yolo26s-seg.pt` (не YOLOE-seg). Маски в SQLite / train не пишутся. JWT: operator / engineer / master.

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/status` | `{ready, loaded, weight, available[], imgsz}` — файл на диске vs модель в VRAM |
| POST | `/load` | `{weight?}` — whitelist имён; без имени — nano, затем small. 400 если не whitelist, 503 если файла нет |
| POST | `/unload` | выгрузить из VRAM (`empty_cache`) |
| POST | `/infer` | кадр JPEG (base64) + `confidence` → `{masks: [{class, conf, polygon_norm}], ms, weight}` |
| POST | `/batch` | batch по ролику: `{video_path, frame_step=30, confidence=0.5, weight?}` → `{task_id, status, progress…}` (один job; 409 если уже running) |
| GET | `/batch/{task_id}` | прогресс; при `done`/`aborted`/`error` — `results: [{time_sec, masks[]}]` |
| POST | `/batch/{task_id}/abort` | прервать job |
| GET | `/sam3/status` | `{ready, loaded, weight, available[]}` — файл `sam3.pt` vs модель в VRAM |
| POST | `/sam3/load` | `{weight?}` — только `sam3.pt`; выгружает YOLO-seg (`yolo_seg_unloaded`) |
| POST | `/sam3/unload` | выгрузить SAM3 |
| POST | `/sam3/infer` | JPEG + (`points`/`bboxes` **XOR** `text` 1–3) → `{masks, ms, weight}` |
| POST | `/sam3/propagate` | `{video_path, time_sec, max_frames≤30, points?/bboxes? **XOR** text?, persist?=false}` → job |
| GET | `/sam3/propagate/{task_id}` | прогресс; terminal → `results`, `persisted` |
| POST | `/sam3/propagate/{task_id}/abort` | прервать |

**SAM3 (P3.13.3a/b):** interactive refine + short forward propagate (≤30 frames, `SAM3VideoPredictor` temp clip). Mutual VRAM с YOLO-seg. Не Live, не train. Opt-in SQLite `seg_masks`. Импорт: `from ultralytics import SAM`; video: `from ultralytics.models.sam import SAM3VideoPredictor`.

`ready` = файл есть; `loaded` = модель в памяти. **Infer/propagate требуют `loaded`** (иначе 503). Batch: если модель уже в VRAM — оставляет; если batch сам загрузил — выгружает в `finally`. Старт batch выгружает SAM3 (`sam_unloaded`) — UI toast, без auto-reload. Нет файла → 503, детекция не меняется. `imgsz=640`. Маски batch **не** пишутся в SQLite. Propagate `persist=true` пишет только в `seg_masks` (не `detections`).

## Change Detection — `/api/change-detection` (Compare Sync)

Сравнение двух архивных роликов (Было/Стало) по сохранённым детекциям. JWT: operator / engineer / master.

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/analyze` | GPS-matching детекций ± `time_window_sec` + ORB/diff fallback |
| POST | `/sync` | Auto time sync: GPS tracks → detections fallback → сегменты |
| GET | `/export` | HTML или KML отчёт (re-run `analyze_pair` по query params) |
| POST | `/batch` | P3.15.5 пакетный CD: `auto_sync` → subsample пар → `analyze_pair` |
| GET | `/batch/{task_id}` | прогресс; при terminal — `results[]` + `aggregate` |
| POST | `/batch/{task_id}/abort` | прервать |
| GET | `/batch/{task_id}/export` | HTML отчёт агрегата (только `status=done`) |

`GET /export` query: `format=html|kml`, `video_before`, `video_after`, `time_before`, `time_after`, опционально `tolerance_m`, `moved_m`, `time_window_sec`. Ответ — attachment (`text/html` или `application/vnd.google-earth.kml+xml`).

Тело `/sync`:

```json
{
  "video_before": "clip_a.mp4",
  "video_after": "clip_b.mp4",
  "source": "auto",
  "tolerance_m": 15.0
}
```

`source`: `auto` | `tracks` | `detections`. Ответ: `{ method_used, pairs[:50], segments[], message, pair_count_total }`.

Тело `/analyze`:

```json
{
  "video_before": "clip_a.mp4",
  "video_after": "clip_b.mp4",
  "time_before": 12.5,
  "time_after": 8.0,
  "tolerance_m": 10.0,
  "moved_m": 3.0,
  "time_window_sec": 0.5,
  "use_gps": true,
  "use_image_fallback": true
}
```

Ответ `/analyze`: `{ method, aligned, message, summary, matches[], new[], removed[], image_diff? }`.

- `method`: `gps` | `image` | `hybrid` | `none`
- `summary`: `{ total_before, total_after, matched, stable, moved, new, removed }`
- `matches[]`: `{ before_id, after_id, class_name, distance_m, status, before_bbox, after_bbox }`
- `image_diff` (только image/ORB path): `{ inlier_ratio, regions[], heatmap_b64? }` — `heatmap_b64` это PNG (JET colormap) в base64 без `data:`-префикса (P3.15.4)
- Классификация: stable (<3 m), moved (3–10 m), new/removed (нет GPS-пары)
- Frontend при Sync передаёт `time_window_sec=0.5`, без Sync — `2.0`

### Batch CD (P3.15.5)

Тело `POST /batch`:

```json
{
  "video_before": "clip_a.mp4",
  "video_after": "clip_b.mp4",
  "source": "auto",
  "pair_stride": 1,
  "max_pairs": 50,
  "use_image_fallback": false
}
```

Один in-memory job (409 если уже `running`). По умолчанию ORB off. `aggregate`: `unique_new/removed/moved` + суммы по парам. `heatmap_b64` из результатов стрипается. UI: кнопка «Пакетный CD» в Compare Sync.

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
| GET | `/hardware` | CPU/GPU/VRAM (`vram_*_mb` / `vram_*_gb`, `gpu_name`, operator+) |
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
| POST | `/api/geo/import` | `{ video_path }` → парсинг sidecar, upsert `flight_tracks`, backfill `gps_*` (`backfilled`). Нет SRT/CSV → **200** `{ sidecar_missing: true, point_count: 0, points: [] }` (не 404) |
| GET | `/api/geo/track?video_path=` | точки траектории (предпочтительно для Windows-путей) |
| GET | `/api/geo/track/{video_path}` | то же через path |
| GET | `/api/geo/detections?video_path=` | детекции + GPS |
| GET | `/api/geo/detections/{video_path}` | то же через path |
| POST | `/api/geo/interpolate` | `{ video_path, time_sec }` → одна точка |

Sidecar: тот же stem, что у видео (`.SRT`/`.srt`, затем `.CSV`/`.csv`), только под `archive/`.

Панель **Гео 3D** (`flight3d`) читает track/detections и рисует three.js-сцену (локальная ENU-проекция, без CDN).

## Detections — `/api/detections`

`GET` требует `source_video` (без него возвращает пустой список; `all_videos=true` только для служебных инструментов). CRUD + `POST /commit` (пакет кадра + crops), `GET /{id}/crop`. Массовый soft-delete: `DELETE ?source_video=...&all=true`.

`GET /export?source_video=` — CSV всех неудалённых детекций ролика (operator+). Первая строка-комментарий: `# Coordinates normalized [0-1]…`. Колонки: `time_sec,class_name,confidence,x1,y1,x2,y2,gps_lat,gps_lon` (bbox из `bbox_x/y/w/h` → xyxy в [0–1]). Кнопка «Экспорт CSV» в Inspector.

`POST /find-similar` — `{ detection_id, top_k?, same_class? }`. Ищет похожие кропы по CLIP `encode_image` (если пакет `clip` и локальный кэш `ViT-B-32.pt` уже есть) иначе `hist+class`. Ответ: `{ query_id, method, same_class, results[] }` где `method` = `clip` | `hist+class`. Векторы кэшируются в `detection_embeddings`. `mobileclip2_b.ts` — текстовый энкодер YOLOE, кропы им не кодируются.

`POST /` и `POST /commit` при наличии sidecar/трека пишут `gps_lat` / `gps_lon` / `gps_alt` (интерполяция по `time_sec`). Ошибка гео не блокирует фиксацию.

## Train / Export

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/train/start` | `{ epochs?, resume_from?, imgsz?, batch?, use_uav_arch?, use_uav_ghost_arch? }` |
| GET | `/api/train/checkpoints` | last/best/epoch*.pt, `can_resume`, `vram_mb` |
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
| GET | `/ollama/status` | state: disconnected/searching/connected/degraded + base_url/model |
| POST | `/ollama/connect` | лестница discovery или `{host,port,base_url,model?}` |
| POST | `/ollama/disconnect` | отключить (настройки в config/local сохраняются) |
| POST | `/ollama/scan` | LAN /24 TCP:11434 (только по запросу, ≤10 с) |
| PUT | `/ollama/settings` | сохранить host/port/model/timeout (+ connect_now) |
| GET | `/models` | список моделей (available только если подключена) |
| POST | `/analyze` | prompt + optional image → текст |
| POST | `/autolabel` | `{ detection_id, model? }` → структурированное предложение класса |

503, если Ollama не подключена. Конфиг: `config/local/ollama.json` (не в git).

## Live — `/api/live`

`POST /open`, `DELETE /{viewer_id}`, `GET /status`, `GET /{viewer_id}/frame`, `GET /{viewer_id}/mjpeg`.

`GET /{viewer_id}/status` возвращает `active=false`, если поток завершился, thread умер или не появился первый кадр за open-timeout.

## REC — `/api/rec`

`POST /start`, `POST /stop`, `GET /status`, `GET /list` → `archive/recordings/`.

## Reports / Models / System / Debug

- `GET /api/report/html` — автономный HTML-отчёт  
- `GET /api/report/pdf` — технический PDF (схема lon/lat + таблица; карта в KML)  
- `GET /api/models/status`, `POST /api/models/import`, `GET /api/models/import/stream`  
- `GET /api/models/usb-scan` — съёмные диски, `.pt`/`.yaml` с валидацией (engineer+)  
- `POST /api/models/usb-import` — `{source_path, target_type: model|classes, confirm}`. `confirm=false` — dry-run; `confirm=true` — copy + `.backup` + `force_load` / `refresh_catalog`  
- `GET /api/system/hardware`, `POST /api/system/selftest`, `POST /api/system/simulate-failure`  
- `GET /api/health` — liveness + YOLO/DB
- **Session Trace (KEEP):** `GET /api/debug/stream`, `GET /api/debug/recent`, `GET /api/debug/trace/file?tail=50`, `POST /api/debug/trace/toggle` `{enabled}`, `GET /api/debug/trace/status`. Header `X-Muravei-Trace-Id`. Env `MURAVEI_SESSION_TRACE`.

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

`GET /status` и SSE (`/stream`) несут live поля: `job_id`, `phase` (`starting`/`extracting`/`colmap`/`export_poses`/…), **`stage`** (`plan` / `feature_extractor` / `sequential_matcher`|`exhaustive_matcher` / `mapper` / `model_converter` / `export_poses` / …), `progress`, `message`. На длинном `mapper` backend поллит `archive/recon/{job}/colmap/sparse/N` и обновляет message (`models=…`, last write); stream шлёт status-heartbeat ~2 с. UI ops-модалка берёт `job_id` из этих полей, не из устаревшего manifest.

Train (один job за раз; блокирует `POST /start` COLMAP пока идёт train):

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/train/presets` | профили из `config/train_presets.json` + VRAM/CUDA/weights gate (`disabled` + RU `disabled_reason`; DA3: `da3_dense_base`/`da3_dense_large`) |
| GET | `/train/status` | текущий train state |
| POST | `/train/start` | `{ job_id, preset }` — 409 если уже train/COLMAP; **503** `DA3_WEIGHTS_NOT_FOUND` если DA3 preset без sidecar |
| POST | `/train/stop` | остановить subprocess |
| GET | `/train/stream` | SSE progress (steps/loss/psnr/vram; DA3 stages `da3_depth`/`da3_fusion`/`da3_done`) |

`GET /api/system/hardware` включает блок `da3` (`present`, `base_present`, `large_present`, paths).

## Network — `/api/network`

Репликация целей и чата между машинами. Инстанс `mode=server` — хаб. `mode=client` — фоновый worker (`backend/services/network_sync.py`, тик **15 с**): heartbeat (реальный LAN IPv4 или `MURAVEI_NETWORK_ADVERTISE_IP`), push/pull targets, затем push/pull messages. Worker стартует всегда; тик no-op, если режим не `client`. Подробности: [NETWORK_REPLICATION.md](NETWORK_REPLICATION.md).

Клиент логинится на хаб `POST /api/auth/login` с сохранённым `hub_pin` (PIN роли на хабе, обычно operator).

| Метод | Путь | Роль | Описание |
|-------|------|------|----------|
| GET | `/config` | operator+ | `mode`, `server_ip`, `port`, `base_name`, `base_id`, `has_hub_pin`. Значение PIN **не** возвращается |
| POST | `/config` | engineer+ | Тело: `mode`, `server_ip`, `port`, `base_name`; опционально `hub_pin` (write-only) |
| GET | `/status` | operator+ | + `advertise_ip`, `sync_interval_sec`, `hub_reachable`, `worker_alive` |
| GET | `/bases` | operator+ | реестр heartbeat (ожидается LAN IP клиента) |
| POST | `/heartbeat` | operator+ | `{base_id, base_name, ip}` |
| GET | `/targets` | operator+ | TTL 24 ч; `?since=<epoch>` |
| POST | `/targets` | operator+ | `direction=out`; опциональный `id`; GPS/`source_video` |
| GET | `/messages` | operator+ | чат; `?since=<epoch>` для инкрементального pull |
| POST | `/messages` | operator+ | `direction=out`; опциональные `id`, `sender`, `created_at` (идемпотентно) |
| GET | `/messages/unread` | operator+ | `{count}` входящих с `created_at > since` |

Цели несут GPS и `source_video`. `crop_path` — путь, байты кропа не гоняются. Messages: `synced_at` / TTL 24 ч; upsert newer-wins.

## Events — `/api/events`

Единая лента для операторского экрана 4×Live: локальные детекции + входящие сетевые цели (`network_targets.direction='in'`). Сортировка по `created_at` (wall-clock), не по видео-`time_sec`. Окно и лимит режутся на бэкенде (window 10–86400 с, limit 1–200).

| Метод | Путь | Роль | Описание |
|-------|------|------|----------|
| GET | `/timeline` | operator+ | Query: `window` (сек, default 300), `limit` (default 100). Ответ `{ events: [...] }`. Каждый элемент: `id`, `type` (`local_detection` \| `network_target`), `time_sec` (видеовремя; `null` у сети), `class_name`, `confidence`, `source_video`, `source_base` (`null` у локальных), `created_at`, плюс `gps_lat`/`gps_lon`/`notes` |

Исходящие цели (`direction=out`) и soft-deleted детекции не попадают в ленту. Индексы: `idx_det_created`, `idx_net_targets_created`.

## Support

`POST /api/support/diagnostic-zip` — железо + логи без PIN.
