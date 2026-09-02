# Тестирование

Правило окружения: только `muravei_env\Scripts\python.exe` (Python 3.12.10) — см. [.cursor/rules/muravei-python-env.mdc](../.cursor/rules/muravei-python-env.mdc). Bare `python`/`pip` использовать нельзя (PATH предпочитает системный 3.14).

## Frontend / E2E — Playwright

Конфиг: [playwright.config.ts](../playwright.config.ts) — channel `chrome`, `workers: 1`, auto-старт backend:8000 + vite:3000 (`reuseExistingServer`), traces/screenshots при падении.

| Команда | Что запускает |
|---------|---------------|
| `npm run test:field` | все 6 приёмочных: `yolo-scrub-gate` + `field-regression` + `recon-raycast` + `test_ui_toggles` + `test_hotkeys` + `test_event_timeline` |
| `npm run test:yolo-scrub` | только YOLO scrub gate |
| `npm run test:yolo-scrub-gate` | alias scrub gate |
| `npm run test` / `npm run test:all` | **единый оркестратор** (unit + compileall + build + smoke + E2E) → `reports/test_report.html` |
| `npx playwright test` | все тесты из `tests/` |

Тесты в [tests/](../tests/):
- `yolo-scrub-gate.test.ts` — suspend YOLO при scrub, cooldown 400мс, WS ignore до parse, paused ≤1/500мс.
- `field-regression.test.ts` — scoped N, Compare Sync, REC, Live, Network `source_video=`.
- `recon-raycast.test.ts` — COLMAP intrinsics, splat pick, miss→toast.
- `test_ui_toggles.test.ts` — тумблеры SAHI/валидатора в AdminPanel: toggle → save → SQLite → API → переживает F5.
- `test_hotkeys.test.ts` — Space, стрелки, 1–4, I/O, guard ввода в input, Ctrl+Z undo patch.
- `test_event_timeline.test.ts` — пресет 4×Live (4 Viewer), лента событий, seek по клику на локальную детекцию.

## Backend — unittest

Без pytest/conftest. Запуск из `backend/`:

```powershell
cd backend
..\muravei_env\Scripts\python.exe -m unittest discover -s tests
```

Или поимённо:

```powershell
..\muravei_env\Scripts\python.exe -m unittest tests.test_validator tests.test_sprint4 tests.test_colmap_poses
```

Файлы в [backend/tests/](../backend/tests/):
- `test_validator.py` — Response Validator, 15 кейсов (включая graceful degradation, JSONL-запись).
- `test_validator_catalog_refresh.py` — автообновление кэша валидатора после правки класса (6 кейсов PUT/DELETE) + TTL 300 с (expiry, within-TTL, refresh bypass, failure keeps cache).
- `test_sprint4.py` — `parse_autolabel_result` (catalog scoping, confidence clamp).
- `test_colmap_poses.py` — COLMAP camera models, `_quat_to_rot`, `nearest_pose`.
- `test_geo_export.py` — KML XML (escape, lon/lat/alt), GeoJSON FeatureCollection, skip без GPS, детерминированный цвет класса.
- `test_geo_persist.py` — attach_gps (интерполяция, keep explicit, no-track), persist в SQLite, backfill только null.
- `test_similarity.py` — cosine ranking, кэш embedding по mtime, 404 без кропа, hist-путь без CLIP.
- `test_trainer_resume.py` — список last/best/epoch, skip seg, 404 без last.pt, clamp imgsz/batch.
- `test_segmentation.py` — нет веса → not ready; YOLOE-seg игнорируется; load/unload; infer без load → ошибка; mock predict → polygon_norm 0–1, модель остаётся loaded.
- `test_change_detection.py` — haversine, filter_detections_at_time, align_by_gps (stable/moved/new/removed), diff_mask, ORB checkerboard (8 тестов).
- `test_time_sync.py` — sync_by_gps_track, sync_by_detections, group_into_segments, auto_sync fallback (4 теста).
- `test_change_export.py` — HTML summary tables; KML folders/Placemarks; no-GPS empty Placemarks (3 теста).
- `test_usb_import.py` — валидация .pt (nc 12/238) и YAML, dry-run без копии, confirm + `.backup`.

## SAHI

```powershell
.\muravei_env\Scripts\python.exe backend\scripts\test_sahi_inference.py
```

Сравнивает `engine.infer()` vs `engine.infer_sahi()`, пишет `logs/sahi_test.json`, PASS если SAHI-путь отработал без ошибки (`sahi=true`).

Полевой тест на сыром кадре БПЛА:

```powershell
.\muravei_env\Scripts\python.exe backend\scripts\test_sahi_field.py
```

Извлекает кадр из `archive/video_2026-08-25_09-17-15.mp4` (fallback — крупнейший recon-кадр), сравнивает fast vs SAHI 512×512/0.2 vs 640×640/0.2, пишет `logs/sahi_field_test.json` + `logs/sahi_field_frame.jpg`, печатает вердикт (`SAHI GAIN` / `NO GAIN / NEUTRAL` / `SAHI LOSS`). Observational — не ассертит прирост.

## Smoke-скрипты

Полный перечень — [SMOKE_TESTS.md](SMOKE_TESTS.md). Запуск:
```powershell
.\muravei_env\Scripts\python.exe backend\scripts\smoke_<name>.py
```

## Сборка (gate)

```powershell
npm run build
```
`tsc` (проверка типов) + `vite build`. Должен быть зелёным перед коммитом.

## Порядок проверок перед коммитом

1. `npm run build` — TypeScript/типы.
2. `python -m unittest discover -s tests` (из `backend/`) — backend unit.
3. `npm run test:field` — приёмочные E2E.
4. `smoke_lbs_ft.py` — быстрый путь YOLO.
5. `test_sahi_inference.py` — SAHI-путь.

Либо одной командой (оркестратор):

```powershell
npm run test
```

(`npm run test` — алиас `npm run test:all`; тот же `scripts/test_orchestrator.py`.)

Запускает последовательно: backend unit → compileall → frontend build → smoke_lbs_ft → test_sahi_field → `npm run test:field`. Генерирует `reports/test_report.html` + `reports/test_report.json`, exit 0 только если все **обязательные** шаги зелёные (smoke/E2E — skip-tolerant: GPU/браузеры могут отсутствовать).

## Pre-commit hook

Быстрый гейт перед коммитом (backend unit + compileall, без smoke/E2E):

```powershell
bash scripts/install-hooks.sh   # установка .git/hooks/pre-commit (идемпотентно)
```

Обход на один коммит: `git commit --no-verify`.

## Отчёты

- Playwright: `playwright-report/` (HTML), `test-results/` (traces/screenshots), `.last-run.json`.
- Smoke: `logs/smoke_*.json`.
- Валидатор: `logs/validator_rejections.jsonl`.
- SAHI: `logs/sahi_test.json`, `logs/sahi_field_test.json`, `logs/sahi_field_frame.jpg`.
- Оркестратор: `reports/test_report.html`, `reports/test_report.json`.
