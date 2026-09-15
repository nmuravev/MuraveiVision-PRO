# TODO — приоритизированный план

Оба мастерплана (`masterplan_field_readiness` A–I, `mosaic_yolo_davinci` Фазы 0–10), **Response Validator**, **Masterplan v3**, и **Phase 3 / P3** (seg + change detection + SAM3 3a/3b) завершены и подтверждены тестами. Ниже — оставшаяся работа по приоритетам. Ограничения без плана — в [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

> Примечание: предыдущий `REMAINING_WORK.md` ошибочно отмечал Response Validator как нереализованный — **исправлено**: валидатор реализован, протестирован (15 unit-тестов), задокументирован в [API.md](API.md).

## Критические баги

На данный момент открытых критических багов нет.

## Packaging (после v3.3 rc)

- [ ] **FullKit CUDA flavor** — seed `portable/cache/wheels` with `torch*+cu128*` (no runtime network); rebuild FullKit cuda zip
- [ ] Локальный split `FullKit_Core` + `FullKit_AliceVision` (bootstrap находит sidecars; **не** GitHub assets)
- [ ] **Tactical YOLO26 s/m/l-ft training** (tank/BMP/soldier/mines) → drop into `assets/models`; rebuild picks up via ladder. **Do not** fetch COCO stock s/m/l.
- [x] **DA3 Dense Backend Phase 1** — integrated on `feature/studio-v3.4-da3` (pose-conditioned, sidecar-only, optional inventory)
- [ ] **DA3 weights fetch** — replace `FETCH_REAL_SHA_AFTER_FIRST_DOWNLOAD` after first download; field real-inference smoke
- [ ] **DA3 rescue / metric scale** — backlog after Phase 1

## Backlog (после Phase 3)

**Phase 3 / P3 закрыт** — см. [PHASE3_FINAL_RETRO.md](PHASE3_FINAL_RETRO.md). SAM3 линия 3a/3b/3c закрыта. Unit + Playwright E2E; error catalog.

### 1. Performance (P2)

- [ ] Profiling batch seg / SAM propagate на 8 ГБ
- [ ] Полевой smoke: archive SAM3 text + Live «Кадр SAM» + Compare Sync на реальных роликах

### 2. По запросу

- [ ] GeoTIFF/KML масок batch/propagate
- [ ] Full-video propagate (сейчас только ≤30 frames)
- [ ] Новые фичи от пользователей

## P3.13 / P3.15 — DONE

- [x] Seg v1.1 archive load/unload + frame (`ea881fc`)
- [x] Batch segmentation (P3.13.2) (`2f7a86c`)
- [x] SAM3 interactive refine (P3.13.3a) (`8baa39f`)
- [x] SAM3 short propagate (P3.13.3b) (`b533f0d`)
- [x] SAM3 text + Live freeze (P3.13.3c)
- [x] Change Detection v1 (`a798b15`)
- [x] Auto Time Sync (P3.15.2) (`8279f8f`)
- [x] HTML/KML export (P3.15.3) (`8f93bb1`)
- [x] Diff heatmap (P3.15.4) (`8b2ff99`)
- [x] Batch Change Detection (P3.15.5)
- [x] Playwright E2E seg/CD (`4aa75af`)
- [x] Error reference system (`7a30f1d`)

## Улучшения / оптимизация (потом)

Открытых пунктов техдолга 5.2 / 5.3 нет — оба закрыты (см. ниже).

- Quick-start guide для полевых инженеров (по желанию)

## Фичи будущего (когда остальное готово)

- Полный пор OpenReel WebGPU/effects.
- Native multi-monitor windows.
- OCR-only телеметрия (расширение geo-scope).
- Cloud/SaaS-режим (если потребуется).

## Закрыто (контекст)

- Мастерпланы A–I, mosaic Фазы 0–10 — DONE.
- SAHI — DONE (`test_sahi_inference.py` PASS). **Баг SAHI исправлен** (`slice_image` patch для 0.12.6) — `test_sahi_field.py` PASS на сыром кадре из дрон-видео.
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
  - `POST /api/scan/start` + SSE, `origin=batch_scan`, кнопка «Сканировать» во Viewer (I–O или весь ролик).
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
  - Batch + SAM3 3a/3b — см. таблицу выше и [PHASE3_FINAL_RETRO.md](PHASE3_FINAL_RETRO.md).
- **Change detection (P3.15)** — DONE:
  - v1 analyze + v2 sync/export/heatmap — см. коммиты в [ROADMAP.md](ROADMAP.md).
- **AliceVision / 3D v3.2 (branch `feature/alicevision-v3.2`)** — DONE (не в main):
  - Dense/Mesh sidecar + soft-fail gates; multi-model `get_best_sparse_dir` (**points3D size primary**, views secondary).
  - Offline env packs `win_cpu` / `win_cuda`; CPU profile + YOLO DirectML (AMD/Intel). См. [ALICEVISION.md](ALICEVISION.md), [SPEC_FIELD_MACBOOK.md](SPEC_FIELD_MACBOOK.md), [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md).
