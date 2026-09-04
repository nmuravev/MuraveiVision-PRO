# Возможности (реализовано)

Что уже работает и протестировано. Подтверждения — в [TESTING.md](TESTING.md) и [SMOKE_TESTS.md](SMOKE_TESTS.md). Детали операций — [OPERATOR_GUIDE.md](OPERATOR_GUIDE.md).

## Интерфейс

- **Mosaic docking** — layout-дерево `react-mosaic-component`, перетаскивание за title bar, 5 drop-зон, snap-split, вкладки, maximize/collapse, float/redock. Пресеты 1/2/4 Viewer и **4×Live**. Layout переживает F5 (`localStorage`). Поведение как в Adobe Premiere. Тулбар Viewer: при ширине &lt; ~980px вторичные кнопки (сегментация/SAM, векторы, Было/Стало, статус, REC/I–O) складываются в меню **«Ещё»** — play/YOLO/скан остаются на панели; dropdown Detect/«Ещё» поверх видео (`overflow-visible` + z-index).
- **Вкладки TopBar** — одна полоса: Медиа / Монтаж / AI-анализ / Обучение / **4×Live** / Система · Экспорт / Раскладка / Окна / Гео 3D / Трассировка / Отладка. Подписи скрываются ниже `md` (иконки + title). Горизонтальный скролл при нехватке места; кнопка **«Ещё»** убрана. Статус YOLO/Ollama/роль — в меню аватара. VRAM у аватара.
- **4×Live + Event Timeline** — 2×2 Viewer (по умолчанию режим Live, стримы не стартуют сами) + лента событий снизу. Опрос `GET /api/events/timeline` каждые 3 с. Клик по локальной детекции: фокус Viewer с тем же `source_video` и seek к `time_sec`. Клик по сетевой цели: карточка (база, GPS, заметки), без seek. Пресет «4 вьюера» в меню Раскладка (пул + инспектор + таймлайн) **не** заменён. Chrome Timeline: Zoom pinned справа; длинные I/O labels скрываются при узкой панели (&lt;720px).
- **Горячие клавиши оператора** — Space play/pause, ←/→ кадр (Shift ×10), I/O метки, F/Ctrl+S фиксация кадра, 1–4 вьюер, Ctrl+Z undo правки детекции, Del удаление. Не срабатывают в input/textarea. Подсказки: меню «Окна».
- **Session Trace (FE+BE)** — сквозная трассировка: клики/hotkeys, `/api` (с `X-Muravei-Trace-Id`), WS summary (не каждый кадр YOLO), store (throttle 500 ms), BE middleware → `logs/trace.log` + pipeline hooks (scan/recon/geo/CD). Dock «Трассировка» в TopBar: REC/Пауза/Метка/JSON. FIFO 500. **Код не удалять** без явного приказа «удали session trace».

## Медиа

- **Архив** — дерево `archive/`, загрузка, корзина, восстановление, безвозвратное удаление.
- **Стрим** — HTTP byte-range streaming (`206`, `Content-Range`) для перемотки и Compare Sync.
- **Filmstrip** — миниатюры таймлайна.

## Детекция (YOLO)

- **YOLO26/YOLOE** — closed-set инференс + COCO-fallback + tiling. WebSocket `/ws/detect/{viewer_id}` → overlay bbox на canvas. Кнопка **YOLO вкл/выкл** во Viewer (архив и Live): выкл — без WS. Не путать с режимом overlay «Детекция» и кнопкой **«Сканировать»**.
- **HUD auto-exclusion** — авто-исключение OSD/телеметрии дрона (полосы по краям). Архив/скан/CD/recon: **по умолчанию ВКЛ**; Live WS: **ВЫКЛ**. Маска = blur/feather (не чёрные прямоугольники); bbox остаются в полном кадре. Recon **кропает** кадры; `manifest.hud_crop` + poses в full-frame. Кэш `archive/analysis/…/hud_zones.json` (fingerprint size+mtime). Toggle в SYSTEM → Конфигурация детекции; Viewer — зоны + бейдж.
- **Сегментация архива (P3.13)** — тумблер Viewer «Детекция / Сегментация» только в Архиве. Явные `POST /api/seg/load` / `/unload` (VRAM). Кнопка «Сегментировать кадр» → полигоны SVG. **Batch сегментация (P3.13.2)** — шаг кадров по ролику, прогресс в модалке, seek по результату; маски in-memory, не в train. **SAM3 refine (P3.13.3a)** — `sam3.pt`, точка / «SAM из детекции»; mutual VRAM с YOLO-seg. **SAM3 propagate (P3.13.3b)** — вперёд ≤30 кадров, opt-in `seg_masks`. **SAM3 text + Live freeze (P3.13.3c)** — text prompts (`trench / окоп; …`), archive «По тексту»; Live «Кадр SAM» = JPEG-capture + временный SVG поверх detect (без unload Detect, без continuous SAM). Auto-infer нет. Live `/ws/detect` не трогаем.
- **Change Detection (P3.15)** — в режиме Было/Стало: «Синхронизировать» (P3.15.2) + «Анализ изменений» (GPS/ORB) + экспорт HTML/KML из Inspector (P3.15.3) + тумблер «Теплокарта» (P3.15.4) + **«Пакетный CD»** (P3.15.5: subsample пар `auto_sync` → `analyze_pair`, aggregate unique IDs, HTML export). Detect/train/seg не затрагиваются.
- **YOLO scrub gate v2** — suspend YOLO при scrub (400мс cooldown), WS ignore до parse, paused ≤1/500мс, seek debounce 100мс. Debug API: `window.muraveiDebug`, `getYOLOStats`, `printYOLOReport`. Визуальный overlay в dev-режиме.
- **SAHI** — нарезка кадра для мелких объектов (4K БПЛА). Опционально: per-request `use_sahi` или системный `use_sahi_default`. Переиспользует модель (без дубля VRAM). Полевой тест: `backend/scripts/test_sahi_field.py` на сыром кадре из дрон-видео → `logs/sahi_field_test.json`.
- **Response Validator** — defense-in-depth фильтр детекций (bbox/conf/area/class_id), JSONL-лог отбросов, graceful degradation. Кэш каталога классов автообновляется после правки `PATCH/DELETE /api/classes/overrides/{id}`.
- **Конфигурация детекции (UI инженера)** — тумблеры/инпуты SAHI (`use_sahi_default`, slice, overlap) и валидатора (`validator_enabled`, min/max bbox area, min confidence) в панели «Система» → «Конфигурация детекции». Сохранение через `PUT /api/system/detect-config` в SQLite, применение без перезапуска, переживает F5.
- **Импорт модели** — загрузка `.pt` через AdminPanel + **USB Offline Model Manager**: сканирование съёмного диска, валидация nc ∈ {12, 238}, confirm + `.backup`, `force_load` без рестарта.

## Работа с детекциями

- **Пакетный скан архива** — фоновый YOLO (~1 fps) по кнопке **«Сканировать»** во Viewer (архив). **4K:** SAHI. Сегмент **I–O** или весь ролик. Кропы + маркеры на таймлайне. Без авто-старта при открытии MP4.
- **CRUD** — создание/правка/удаление, soft-delete, bulk «Очистить».
- **Галерея кропов** — **треки** (клиентский greedy: class + Δt≤2.5с + IoU/центр): карточка `class · in→out`, клик ставит I/O и seek. Покадровый список — в Inspector «Все кадры». БД без миграции.
- **Scoped-фильтр по видео** — Inspector/Gallery/Viewer/TopBar показывают N текущего ролика.
- **Inspector** — список детекций, заметки (debounce), флаг, выбор класса при рисовании, **«Экспорт CSV»** (`GET /api/detections/export`, координаты нормализованы [0–1]).
- **VRAM в TopBar** — индикатор `VRAM: used/total ГБ` (poll `GET /api/system/hardware` каждые 5 с; цвет по свободному VRAM).
- **Find-similar** — Inspector «Найти похожие»: CLIP `encode_image` если веса уже на диске, иначе гистограмма. Превью кропа, переход на другой ролик. Кэш векторов в SQLite. `mobileclip2_b.ts` для YOLOE-text, не для поиска кропов.
- **Compare Sync** — два Viewer, drift-correction 500мс, синхронизация воспроизведения.

## AI / аналитика

- **Active Learning** — очередь low-confidence детекций, сбор/решение (accept/reject). API `/api/active-learning`.
- **Ollama autolabel** — предложение класса через Ollama, accept патчит детекцию. API `/api/ai/autolabel`.
- **Rules/alerts** — правила детекции с cooldown 3с. Звук: `beep` / `alarm` / `none`, громкость 0–100, кнопка «Тест». Back-compat: `sound=true` → `beep`.

## Воспроизведение / запись

- **Playback rate** — `<select>` скорости.
- **REC >60с** — запись через ffmpeg, health-check живого процесса.
- **Live** — RTSP/UDP/HTTP, `active`+`thread.is_alive()`, open-timeout (`CAP_PROP_OPEN_TIMEOUT_MSEC`).

## Сеть

- **Network sync** — реальная репликация между машинами: фоновый worker, JWT на хаб, инкрементальный pull `GET /targets?since=`, upsert newer-wins, TTL 24 ч. `source_video` и GPS уезжают вместе с целью. API: `/api/network/config` (`hub_pin` write-only), `/api/network/status`, `/api/network/targets`.

## Фотограмметрия (C.1–C.5)

- **COLMAP** — poses + intrinsics (PINHOLE/SIMPLE_PINHOLE/SIMPLE_RADIAL/RADIAL/OPENCV).
- **gsplat** — UI train presets (Balanced/Bootstrap/High) + dual load Points / DropInViewer. **Not** run inside «Построить 3D» by default (`GSPLAT_INLINE=1` opt-in only).
- **Flight3D** — ручной scale/horizon. «Построить 3D» = COLMAP sparse (`colmap_done` + `next_action=balanced_for_splat`); ops-модалка: live stages из SSE (`extract` → `COLMAP plan` → `feature_extractor` → matcher → `mapper` с `sparse/N`+last write → `model_converter` → позы → load); header `job` = **текущий** `job_id` из status/SSE (не stale manifest). После sparse: **`sparse COLMAP · нужен train для splat`**. После успешного Balanced `_patch_artifact` снимает `next_action` и UI **не** показывает CTA/баннер, если `artifact=model.ply` (даже при sparse-превью во время загрузки DropIn). Idle-карточка → Balanced. Strip Bootstrap / Balanced / High; HQ disabled при VRAM &lt; 12 ГБ. Один train за раз; взаимная блокировка с COLMAP (**не** с `sceneLoading` splat). Sparse-превью до скачивания `model.ply`. Train-успех держит chip до загрузки splat. Canvas: absolute host + `setSize(w,h,false)` + `overflow-hidden` (без дрожания при сжатии mosaic).
- **2D→3D raycast** — intrinsics + splat pick, miss→toast (не THREE.Raycaster).

## Отчёты / обучение

- **HTML-отчёт** — `GET /api/report/html`.
- **PDF** — `GET /api/report/pdf`: таблица + примитивная lon/lat-схема (не карта Google Earth).
- **Гео v1** — sidecar `.SRT`/`.CSV` рядом с роликом в `archive/` → `flight_tracks` и `gps_*` на детекциях (фиксация кадра, ручная рамка, batch-scan). `POST /api/geo/import` дописывает GPS на старые строки; без sidecar — **200** `{ sidecar_missing: true, point_count: 0 }` (не 404). Повторный import при hydrate того же ролика не дергается. Модалка ошибок не показывается на 404 `/api/geo/import` и `/api/recon/asset/`.
- **KML / GeoJSON** — `GET /api/export/kml?source_video=…` и `/api/export/geojson?source_video=…`. Детекции без GPS пропускаются. KML — основной геоформат (Google Earth). Dropdown «Экспорт» в TopBar.
- **Training/fine-tune** — detect-only, дефолт imgsz 640 / batch 4, resume `last.pt`, `.pt.backup` + `empty_cache`, promote.

## Portable

- **Lite / Full Kit** — embeddable Python 3.12.10, запуск `.bat`. См. [PORTABLE.md](PORTABLE.md).
