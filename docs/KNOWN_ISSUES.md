# Известные ограничения и проблемы

Актуальный список. Запланированные работы — [TODO.md](TODO.md).

## Session Trace (observability)

- **По умолчанию ON** (bug-hunt). Пауза записи — TopBar «Трассировка» / dock; код **остаётся в репо** до явного приказа пользователя: «удали session trace».
- Умные фильтры: нет base64/кадров WS; FE буфер 500; store ≤1/500 ms; WS msg summary ≤1/5 с.
- Файлы: `logs/trace.log`, `logs/runtime.log`. Env `MURAVEI_SESSION_TRACE=0` — пауза BE без удаления middleware.

## Детекции / галерея

- **Полнота скана** пропорциональна плотности (`fps_sample`, по умолчанию ~2). Треки (in→out) **группируют** существующие кадры, но **не создают** детекции между редкими сэмплами.
- SAHI включается для кадров ≥1080p (не только 4K).

## Flaky / окружение

- **`ECONNRESET` на `POST /api/active-learning/collect`** при конкурентных воркерах Playwright. Mitigation: `workers: 1` в [playwright.config.ts](../playwright.config.ts) (уже выставлено). При ручном запуске нескольких тест-наборов против одного backend — возможен reset; перезапустите backend.
- **SAHI `pip check` warning**: `sahi 0.12.6` декларирует `opencv-python>=4.12.0.88` (имя non-headless пакета), но установлен `opencv-python-headless`. `cv2` предоставляется headless-сборкой, runtime работает. Benign — можно игнорировать.

## Не поддерживается (осознанно)

- **Intel Arc/XPU** — не тестируется, провайдеры ORT могут отсутствовать. Только CUDA и CPU.
- **Native multi-monitor windows** — только in-app floating panels; нативных окон на отдельные мониторы нет.
- **Полный пор OpenReel WebGPU/effects** — не переносился; MVP использует `<video>` + frame grab + canvas overlay.
- **OCR-only телеметрия** — вне первоначального geo-scope (SRT/CSV только).
- **Cloud/SaaS/full NLE** — вне скоупа; система локальная, air-gap.
- **Кастомное layout-дерево вместо mosaic** — mosaic остаётся ядром; кастом только chrome/float поверх.

## Производительность

- **SAHI** добавляет N инференсов на кадр (по слайсам). По умолчанию выключен; включать только для тяжёлых 4K-кадров БПЛА.
- **Seg-модель** занимает ~2–4 ГБ VRAM. На RTX 5060 Laptop (8 ГБ) не держать seg и detect одновременно: выгружайте seg (Viewer «Выгрузить» / SEG→Детекция / Admin) перед live-детекцией.
- **SAM3** (`sam3.pt`, ~3.5 ГБ) и YOLO-seg взаимно исключают VRAM; **Detect (YOLO) не выгружается** при load SAM3. Batch seg выгружает SAM3 без auto-reload. Propagate ограничен ≤30 кадрами (temp clip); VideoPredictor / VideoSemanticPredictor могут кратковно увеличить VRAM. Live SAM = только freeze-кадр (не continuous).

## Совместимость

- **Python**: только 3.12.10 (`muravei_env`). Системный 3.14 несовместим — см. [.cursor/rules/muravei-python-env.mdc](../.cursor/rules/muravei-python-env.mdc).
- **numpy**: pinned `<2` (ultralytics/совместимость). SAHI ставится с `--no-deps`, чтобы не тащить numpy 2.x.

## 3D Reconstruction / gsplat

- **COLMAP sidecar auto-detect (2026-09-03):** если `COLMAP_ROOT` не задан, `recon_scanner._colmap_bin()` ищет `sidecars/colmap` (`COLMAP.bat`, `bin/colmap.exe`). Launchers (`npm run backend`, `start-backend.bat`, `Запустить.bat`, `desktop_launcher.py`) выставляют `COLMAP_ROOT` по умолчанию.
- **Multi-model COLMAP sparse/N (2026-09-04):** diagnose / train / bootstrap / `recon_scanner` выбирают лучшую `sparse/N` по размеру `points3D.*` (`get_best_sparse_dir`), а не только `sparse/0`. Нормализация для gsplat: копия в `gsplat_data/sparse/0/`.
- **Job ID / CLI whitespace (2026-09-04):** ID = 12 hex (`uuid4().hex[:12]`). При copy-paste с переносом PowerShell может разрезать аргумент — используйте `$jid = '…'` или положитесь на `sanitize_job_id` / `nargs='+'` join в CLI (`services/job_ids.py`). Генерация ID не менялась.
- **404 `sparse_points.json` / sidecar SRT в модалке (исправлено 2026-09-03):** Flight3D не запрашивает sparse до `colmap_done`/`done`. `POST /api/geo/import` без sidecar отвечает 200 `sidecar_missing`. `apiErrorReporter` молчит на 404 `/api/recon/asset/` и `/api/geo/import` и на заголовок `X-Muravei-Silent-Error`. Переключение вкладок mosaic / dock не должно открывать ErrorDetails. При `manifest.status=error` overlay показывает `manifest.error`. Пока идёт COLMAP — в Гео 3D текст фазы, не «Загрузка 3D-сцены».
- **`preview.ply` ≠ photorealistic splat.** Это цветное облако COLMAP (`THREE.Points`). Фотореализм — вкладка **Сцена** + `manifest.artifact = model.ply` после полного train.
- **Полный 3DGS на Windows (проверено 2026-09-03):** VS Build Tools path `...\18\BuildTools` + **MSVC 14.44** (`vcvars64 -vcvars_ver=14.44`) + CUDA Toolkit **12.8** + `scripts\patch_gsplat_windows_jit.py` + `scripts\run_gsplat_train_windows.ps1`. Без патча JIT падает на `-Wno-attributes` (MSVC) и на `#define small` в Windows SDK → `CUDACachingAllocator.h`. MSVC **19.51** отвергается CUDA 12.8 без `-allow-unsupported-compiler`.
- **Не** ставить `PYTHONHOME` на `muravei_env` (часто пустой `Include/`). Headers — из системного `Python312\Include`.
- Bootstrap `model.ply` (~сотни KB) ≠ полный train (ожидайте **≫ 1 MB** и `"gsplat": true` в `gsplat_meta.json`). Очень маленький ply после 30k = слабый COLMAP (мало Gaussian’ов), не сбой JIT.
- Синие маркеры в режиме **Гео** — playhead cone, не splat.
- Train: ~10–30 мин на сцену (30k steps, RTX 5060).

## Сеть / репликация

- **Один инстанс / одна `muravei.db` не проверяет репликацию.** Два `uvicorn` в одном дереве смотрят в один SQLite и имитируют «синк». Нужны две копии проекта (отдельные БД) на разных портах — процедура в [ENGINEER_GUIDE.md](ENGINEER_GUIDE.md#сеть-баз).
- **Кроп цели** (`crop_path`) — строка пути, JPEG по LAN не копируется; на другой базе превью может быть 404. Это v1, не баг репликации id/GPS/`source_video`.
- **TLS** в приложении нет: JWT по HTTP в LAN. HTTPS — только reverse-proxy, если понадобится.

## Change Detection (P3.15)

- **GPS точность** — matching зависит от качества SRT/CSV и backfill; без GPS (<30% coverage) — ORB fallback, чувствителен к смене освещения/угла камеры.
- **ORB inlier_ratio** — при `<0.25` alignment помечается как failed; partial GPS result сохраняется если был.
- **Heatmap (P3.15.4)** — только на image/ORB path (`image_diff.heatmap_b64`); при чистом GPS high-coverage кнопки «Теплокарта» нет.
- **HTML export Leaflet** — карта в HTML-отчёте тянет Leaflet/OSM CDN; в air-gap таблицы отчёта работают, карта — нет.

## Документация

- Устаревшие манифесты в `.backup/MuraveiVision/*.md` — **не использовать** (другой каркас).
- [`ARCHITECTURE_FOR_AI.md`](ARCHITECTURE_FOR_AI.md) — stub; читать [ARCHITECTURE.md](ARCHITECTURE.md).
