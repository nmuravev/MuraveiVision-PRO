# TODO — приоритизированный план

Оба мастерплана (`masterplan_field_readiness` A–I, `mosaic_yolo_davinci` Фазы 0–10), **Response Validator** и **Masterplan v3 Фаза 1+2** завершены и подтверждены тестами. Ниже — оставшаяся работа по приоритетам. Ограничения без плана — в [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

> Примечание: предыдущий `REMAINING_WORK.md` ошибочно отмечал Response Validator как нереализованный — **исправлено**: валидатор реализован, протестирован (15 unit-тестов), задокументирован в [API.md](API.md).

## Критические баги

На данный момент открытых критических багов нет.

## Следующий спринт

**Phase 3 / P3 закрыт** — см. [PHASE3_FINAL_RETRO.md](PHASE3_FINAL_RETRO.md). 104 unit-теста; P3.15 v2 + E2E + error catalog.

Следующий фокус: **P3.13.3 SAM2** (P2) или полевой smoke batch seg.

### 1. P3.13.3 SAM2 — P2

- [ ] SAM2 / realtime seg / маски в SQLite (см. также «Фичи будущего»)

### P3.13 / P3.15 — DONE

- [x] Seg v1.1 archive load/unload + frame (`ea881fc`)
- [x] Batch segmentation (P3.13.2): `/api/seg/batch`, modal, in-memory results
- [x] Change Detection v2 + E2E + error catalog (см. [PHASE3_FINAL_RETRO.md](PHASE3_FINAL_RETRO.md))

## Улучшения / оптимизация (потом)

Открытых пунктов техдолга 5.2 / 5.3 нет — оба закрыты (см. ниже).

- Performance profiling при 8 GB VRAM
- Quick-start guide для полевых инженеров

## Фичи будущего (когда остальное готово)

- Полный пор OpenReel WebGPU/effects.
- Native multi-monitor windows.
- OCR-only телеметрия (расширение geo-scope).
- Cloud/SaaS-режим (если потребуется).
- SAM2 / realtime seg / маски в SQLite.

## Закрыто (контекст)

- Мастерпланы A–I, mosaic Фазы 0–10 — DONE.
- SAHI — DONE (`test_sahi_inference.py` PASS). **Баг SAHI исправлен** (`slice_image` kwargs для 0.12.6) — `test_sahi_field.py` PASS на сыром кадре из дрон-видео.
- Response Validator — DONE (15 unit-тестов PASS, интеграция в `_finalize_sync`).
- **Masterplan v3 Фаза 1** — DONE:
  - 1.1 Полевой тест SAHI на сыром 4K-кадре БПЛА — `backend/scripts/test_sahi_field.py`, `logs/sahi_field_test.json`.
  - 1.2 UI-переключатели SAHI/валидатора в AdminPanel + `detect-config` API с полями валидатора — Playwright `test_ui_toggles.test.ts` PASS.
  - 1.3 Автообновление кэша валидатора после `PATCH/DELETE /api/classes/overrides/{id}` — `test_validator_catalog_refresh.py` (6 тестов) PASS.
- **Masterplan v3 Фаза 2** — DONE:
  - 2.1 Единый оркестратор тестов — `scripts/test_orchestrator.py` + `npm run test:all` → `reports/test_report.html`, exit 0.
  - 2.2 Pre-commit hook — `.git/hooks/pre-commit` + `scripts/install-hooks.sh` (unit + compileall гейт).
  - 2.3 Тесты фич Фазы 1 — `tests/test_ui_toggles.test.ts` (Playwright) + `test_validator_catalog_refresh.py` (unit).
- **Masterplan v3 Stage 1 (3.4 / 4.2 / 3.3)** — DONE:
  - 3.4 Hotkeys — `src/hooks/useHotkeys.ts`, undo patch-only, Playwright `test_hotkeys.test.ts`.
  - 4.2 Audio cue — `soundType` beep/alarm/none + volume в RulesPanel.
  - 3.3 KML/GeoJSON/PDF — `backend/services/geo_export.py`, `GET /api/export/kml|geojson`, `GET /api/report/pdf`, dropdown TopBar, `test_geo_export.py`.
- **Masterplan v3 3.1 Network replication** — DONE:
  - Demo in/out mirror снят; `POST /targets` пишет одну строку `out`.
  - Worker `network_sync.py` (тик 30 с, JWT, push/pull `?since=`, upsert newer-wins, skip self).
  - `GET /api/network/status`, `hub_pin` write-only, `test_network_sync.py`.
  - Ручной E2E — две копии каталога, см. [ENGINEER_GUIDE.md](ENGINEER_GUIDE.md#сеть-баз).
- **Masterplan v3 3.2 4×Live + Event Timeline** — DONE:
  - `GET /api/events/timeline` — merge локальных детекций и входящих `network_targets`.
  - Пресет/вкладка 4×Live (2×2 Viewer + панель «События»); «4 вьюера» в Раскладке не заменён.
  - Playwright `test_event_timeline.test.ts`, unit `test_events_timeline.py`.
- **TTL кэша валидатора (5.4)** — DONE:
  - `_known_ids()` истекает через 300 с; `refresh_catalog()` по-прежнему мгновенный.
  - При ошибке каталога после TTL сохраняется старый set (backoff, не каждый кадр YOLO).
  - `test_validator_catalog_refresh.py` — 10 кейсов (6 refresh + 4 TTL).
- **USB Offline Model Manager (4.1)** — DONE:
  - `GET /api/models/usb-scan`, `POST /api/models/usb-import` (engineer, confirm + `.backup`).
  - Detect `.pt` → `assets/models/yolo26n-ft.pt` + `force_load`; YAML → `military_classes.yaml` + `refresh_catalog`.
  - `test_usb_import.py`.
- **Code-split frontend (5.1)** — DONE:
  - Lazy: Flight3D, Admin, Network, AI, Train, Debug, Gallery; Suspense в `ComponentForId`.
  - `manualChunks`: vendor-react / mosaic / three / three-examples / splats. Горячий путь (Viewer) в `index` ~176 kB.
  - `npm run build` без warning >500 kB.
- **Консолидация docs (5.2)** — DONE:
  - Один [ARCHITECTURE.md](ARCHITECTURE.md): часть A (слои/потоки) + часть B (инварианты AI).
  - [ARCHITECTURE_FOR_AI.md](ARCHITECTURE_FOR_AI.md) — stub со ссылкой.
- **Алиас тестов (5.3)** — DONE:
  - `npm run test` = `npm run test:all` (`scripts/test_orchestrator.py`).
- **Batch-скан архива (P0.1)** — DONE:
  - `POST /api/scan/start` + SSE, `origin=batch_scan`, авто-старт при открытии ролика без batch-строк.
  - Маркеры timeline (голубые), кропы, прогресс в Timeline/UpdatePanel.
- **Гео v1 на всех детекциях (P0.4)** — DONE:
  - Sidecar SRT/CSV → `gps_*` при create/commit/batch-scan; `POST /api/geo/import` backfill старых строк.
  - `test_geo_persist.py`.
- **Find-similar (P1.6)** — DONE:
  - CLIP `encode_image` при локальном `ViT-B-32.pt`, иначе `hist+class`; кэш `detection_embeddings`.
  - Inspector: превью кропа, jump на другой ролик, бейдж метода. `test_similarity.py`.
- **Resume train UI (P1.8)** — DONE:
  - `GET /api/train/checkpoints`, `POST /api/train/start` принимает `resume_from` / `imgsz` / `batch`.
  - Detect-only, empty_cache, дефолт 640/4. `test_trainer_resume.py`.
- **Archive seg (P3.13)** — DONE:
  - `segmentation_engine.py` + `/api/seg` status/load/unload/infer; Viewer кнопка кадра; Admin load.
  - Полигоны SVG, не train. `test_segmentation.py`.
- **Change detection (P3.15 v1)** — DONE:
  - `change_detection.py` + `POST /api/change-detection/analyze`; Compare Sync UI (кнопка, Inspector, changeOverlays).
  - GPS stable/moved/new/removed + ORB fallback. `test_change_detection.py`.
- **Auto time sync (P3.15.2)** — DONE:
  - `time_sync.py` + `POST /api/change-detection/sync`; CompareSyncModal (сегменты, Auto/GPS/Детекции).
  - Fallback tracks → detections → manual hint. `test_time_sync.py`.
- **Change export (P3.15.3)** — DONE:
  - `GET /api/change-detection/export`; HTML (`change_export.py`) + KML (`geo_export.build_change_kml`).
  - Inspector «Экспорт HTML/KML». `test_change_export.py`.
