# Возможности (реализовано)

Что уже работает и протестировано. Подтверждения — в [TESTING.md](TESTING.md) и [SMOKE_TESTS.md](SMOKE_TESTS.md). Детали операций — [OPERATOR_GUIDE.md](OPERATOR_GUIDE.md).

## Интерфейс

- **Mosaic docking** — layout-дерево `react-mosaic-component`, перетаскивание за title bar, 5 drop-зон, snap-split, вкладки, maximize/collapse, float/redock. Пресеты 1/2/4 Viewer. Layout переживает F5 (`localStorage`). Поведение как в Adobe Premiere.
- **Вкладки TopBar** — MEDIA / EDIT / AI ANALYSIS / TRAINING / SYSTEM (смена mosaic-presets + контента).
- **Горячие клавиши оператора** — Space play/pause, ←/→ кадр (Shift ×10), I/O метки, F/Ctrl+S фиксация кадра, 1–4 вьюер, Ctrl+Z undo правки детекции, Del удаление. Не срабатывают в input/textarea. Подсказки: меню «Окна».
- **DaVinci-визуал** — тёмная тема, серые панели, оранжево-красные акценты playhead/selection.

## Медиа

- **Архив** — дерево `archive/`, загрузка, корзина, восстановление, безвозвратное удаление.
- **Стрим** — HTTP byte-range streaming (`206`, `Content-Range`) для перемотки и Compare Sync.
- **Filmstrip** — миниатюры таймлайна.

## Детекция (YOLO)

- **YOLO26/YOLOE** — closed-set инференс + COCO-fallback + tiling. WebSocket `/ws/detect/{viewer_id}` → overlay bbox на canvas.
- **YOLO scrub gate v2** — suspend YOLO при scrub (400мс cooldown), WS ignore до parse, paused ≤1/500мс, seek debounce 100мс. Debug API: `window.muraveiDebug`, `getYOLOStats`, `printYOLOReport`. Визуальный overlay в dev-режиме.
- **SAHI** — нарезка кадра для мелких объектов (4K БПЛА). Опционально: per-request `use_sahi` или системный `use_sahi_default`. Переиспользует модель (без дубля VRAM). Полевой тест: `backend/scripts/test_sahi_field.py` на сыром кадре из дрон-видео → `logs/sahi_field_test.json`.
- **Response Validator** — defense-in-depth фильтр детекций (bbox/conf/area/class_id), JSONL-лог отбросов, graceful degradation. Кэш каталога классов автообновляется после правки `PATCH/DELETE /api/classes/overrides/{id}`.
- **Конфигурация детекции (UI инженера)** — тумблеры/инпуты SAHI (`use_sahi_default`, slice, overlap) и валидатора (`validator_enabled`, min/max bbox area, min confidence) в панели «Система» → «Конфигурация детекции». Сохранение через `PUT /api/system/detect-config` в SQLite, применение без перезапуска, переживает F5.

## Работа с детекциями

- **CRUD** — создание/правка/удаление, soft-delete, bulk «Очистить».
- **Scoped-фильтр по видео** — Inspector/Gallery/Viewer/TopBar показывают N текущего ролика.
- **Inspector** — список детекций, заметки (debounce), флаг, выбор класса при рисовании.
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
- **gsplat** — train hook, dual load Points / DropInViewer.
- **Flight3D** — ручной scale/horizon.
- **2D→3D raycast** — intrinsics + splat pick, miss→toast (не THREE.Raycaster).

## Отчёты / обучение

- **HTML-отчёт** — `GET /api/report/html`.
- **PDF** — `GET /api/report/pdf`: таблица + примитивная lon/lat-схема (не карта Google Earth).
- **KML / GeoJSON** — `GET /api/export/kml?source_video=…` и `/api/export/geojson?source_video=…`. Детекции без GPS пропускаются. KML — основной геоформат (Google Earth). Dropdown «Экспорт» в TopBar.
- **Training/fine-tune** — `.pt.backup` + `empty_cache`, один callback, promote.

## Portable

- **Lite / Full Kit** — embeddable Python 3.12.10, запуск `.bat`. См. [PORTABLE.md](PORTABLE.md).
