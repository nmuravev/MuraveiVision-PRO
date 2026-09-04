# Известные ограничения и проблемы

Актуальный список. Запланированные работы — [TODO.md](TODO.md).

## Session Trace (observability)

- **RESOLVED (2026-09-04): duplicate React keys on remount** — page-lifetime singleton; `sessionStorage` UUID (`muravei_session_trace_uuid`); event ids `${sessionUuid}-${seq}`; Strict Mode remount does not reset `seq`. KEEP until user says «удали session trace».
- **По умолчанию ON** (bug-hunt). Пауза записи — TopBar «Трассировка» / dock; код **остаётся в репо** до явного приказа пользователя: «удали session trace».
- Умные фильтры: нет base64/кадров WS; FE буфер 500; store ≤1/500 ms; WS msg summary ≤1/5 с.
- Файлы: `logs/trace.log`, `logs/runtime.log`. Env `MURAVEI_SESSION_TRACE=0` — пауза BE без удаления middleware.

## Детекции / галерея

- **RESOLVED (2026-09-04): MediaPool absolute paths** — `/api/media` tree/`file` return `archive/...`; FE `toArchiveMediaPath` / `archiveMediaPath` rewrite Windows/Unix abs under archive. Viewer `sourcePath` is canonical; DB key still via `normalize_media_path` (no `archive/` prefix).
- **Полнота скана** пропорциональна плотности (`fps_sample`, по умолчанию ~2). Треки (in→out) **группируют** существующие кадры, но **не создают** детекции между редкими сэмплами.
- SAHI включается для кадров ≥1080p (не только 4K).

## Flaky / окружение

- **`ECONNRESET` на `POST /api/active-learning/collect`** при конкурентных воркерах Playwright. Mitigation: `workers: 1` в [playwright.config.ts](../playwright.config.ts) (уже выставлено). При ручном запуске нескольких тест-наборов против одного backend — возможен reset; перезапустите backend.
- **SAHI `pip check` warning**: `sahi 0.12.6` декларирует `opencv-python>=4.12.0.88` (имя non-headless пакета), но установлен `opencv-python-headless`. `cv2` предоставляется headless-сборкой, runtime работает. Benign — можно игнорировать.

## Portable build (RESOLVED 2026-09-05)

- **Stale staging / DLL locks:** fixed-name stage dirs + live host uvicorn → `Remove-Item` / robocopy fails. Fix: timestamped `portable/stage_<Kit>_<stamp>/`, purge of `stage_*` / `*.locked_*` at start; stop backend before build; reboot if AV holds DLLs.
- **`cacert.pem` vanishes mid-pip:** staged `python -m pip` self-upgrade deletes vendor CA while `SSL_CERT_FILE` still points at it. Fix: host `pip --python <staged>`; stable `portable/cache/cacert.pem` + env pins.
- **AV breaking staged pip (`INSTALLER*.tmp`):** prefer offline `portable/cache/wheels` (`scripts/cache_portable_wheels.ps1`); robocopy host site-packages only as fallback / `MURAVEI_PORTABLE_MIRROR=1`. See [PORTABLE.md](PORTABLE.md).

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

- **Stale `next_action=balanced_for_splat` after Balanced (RESOLVED 2026-09-04):** `_patch_artifact` писал `model.ply`/`done`, но оставлял `next_action` → после refresh Flight3D держал жёлтый CTA «нужен train» и idle-карточку Sparse, хотя splat уже на диске. Fix: pop `next_action` при `model.ply`; FE banners/CTA gated by `classifyArtifact !== 'splat'`.
- **Inline optional gsplat after Build3D (RESOLVED 2026-09-04):** previously `_try_gsplat_train` (500 steps) ran after COLMAP, usually failed silently → `colmap_done` + `artifact: null` looked like a «reset». Default path **skips** inline train (no `phase=training` SSE); photoreal via Balanced/Bootstrap/High. Opt-in: `GSPLAT_INLINE=1`. Manifest `next_action=balanced_for_splat`; Session Trace `gsplat-inline-skipped`.
- **CSP `blob:` in `connect-src` (RESOLVED 2026-09-04):** `index.html` allows `blob:` in `connect-src` so splat ObjectURL fetch works. **Hard-reload** the browser after pull (`Ctrl+Shift+R`) — CSP meta is cached aggressively.
- **HQ train preset (2026-09-04):** UI profile **High Quality** disabled when total VRAM &lt; 12 ГБ (typical 8 ГБ field laptop → use Balanced or Bootstrap). One gsplat train at a time; blocks «Построить 3D» while training.
- **HUD auto-exclusion (2026-09-04):** border OSD only; large **central** overlays need manual zones. First scan/recon frames may be unmasked until HUD `ready` (non-blocking compute). Fingerprint size+mtime invalidates cache after re-copy.
- **HUD `/api/hud/zones` 404 modal spam (RESOLVED 2026-09-04):** Viewer polled zones every 2.5s; stale uvicorn without `hud` router → FastAPI 404 → ErrorDetails. FE now silent-header + stop poll on ready/404; `apiError` skips `/api/hud/` 404. Restart backend after pull.
- **Recon 409 storm (RESOLVED 2026-09-04):** SSE drop no longer clears `reconRunning` while BE status is `running` — Build stays disabled; re-attaches stream.
- **Balanced/High «exit code 1» without MSVC (RESOLVED 2026-09-04):** gsplat CUDA JIT needs `cl.exe`. UI train now tees `archive/recon/<job>/train.log`, surfaces a stderr snippet (not bare exit code), wraps launch via `vcvars64 -vcvars_ver=14.44` when Build Tools are installed, and **fail-fast** / disables Balanced+High with `disabled_reason` if neither `cl` nor vcvars — use **Bootstrap** or engineer MSVC setup ([ENGINEER_GUIDE.md](ENGINEER_GUIDE.md)).
- **Train API 404 / ErrorDetails modal (RESOLVED 2026-09-04):** `/api/recon/train/*` отсутствует у устаревшего uvicorn → пустые кнопки пресетов + модалка «Ошибка 404» при открытии Гео 3D. Нужен **полный** restart backend после pull. UI: silent 404 + inline «Перезапустите backend» (не глобальная модалка).
- **Stale COLMAP running (RESOLVED 2026-09-04):** после kill/reload uvicorn `_state.status=running` с мёртвым thread → train presets disabled («Дождитесь COLMAP») + `POST /api/recon/start` **409**. `status()`/`start()` теперь recover dead thread → idle. FE: не блокировать train, если manifest уже `colmap_done`/`done`.
- **Train UI stuck at 0/N after backend restart (RESOLVED 2026-09-04):** (1) gsplat tqdm пишет `2123/7000`, а парсер ждал только `step=`/`iter=` → модалка навсегда `0/7000` при живом train; (2) SSE после kill uvicorn закрывается *без* reject → UI не стартовал poll и оставался `training` при уже `idle` API. Fix: parse tqdm bar (игнор downscale `121/121`), heartbeat-сообщения на prep/JIT, stale-train recover в `status()`/`start()`, параллельный status-poll + unlock при 401/idle. Не перезапускайте backend во время Balanced; `npm run backend` без `--reload`.
- **Balanced «жму — ничего» (RESOLVED 2026-09-04):** train buttons были в `disabled` из‑за `opsBlocking` (`sceneLoading` на время скачивания ~40MB `model.ply` / DropIn). Disabled HTML-кнопки не шлют click. Fix: `trainBlocked` без `sceneLoading`; sparse-превью до blob fetch; `startTrain` не silent-return на stale `colmapRunning`. **Follow-up:** `POST /train/start` **409** пока hung COLMAP другого job держал scanner `running` (thread alive в `subprocess.run(mapper)`); optimistic `status=training` + SSE → ошибка 409 мгновенно затиралась в `idle`. Fix: `force_release_for_train` / recover disk-terminal + block COLMAP только для того же `job_id`; не ставить `training` до 200.
- **Train exit 3221225786 / KeyboardInterrupt (2026-09-04):** `uvicorn --reload` или Ctrl+C в консоли backend шлёт CTRL_BREAK дочернему gsplat → exit `0xC000013A`. `npm run backend` теперь **без** `--reload`; для hot-reload: `npm run backend:watch`. `format_train_error` объясняет interrupt; после сбоя train manifest остаётся `done`/`colmap_done` (не `error`), чтобы Balanced оставался доступен. Orphan COLMAP после detach: `terminate_colmap_for_job` (psutil per-PID, не `taskkill /IM`). Scrub orphan manifests не трогает job живого worker даже если `_state` уже `idle`.
- **Ops progress modal stuck on one COLMAP phrase (RESOLVED 2026-09-05):** ранее UI держал stale `job_id`/message (~30 мин на одной фразе). Fix: SSE/status несут live `job_id`+`stage`; mapper поллит `sparse/N` (`models=…`, last write); heartbeat ~2 с; ops-модалка берёт progress meta из stream, не из старого manifest.
- **Ops progress modal log tail:** last **20** SSE/message lines only. COLMAP stages теперь live из backend `stage` + mapper sparse poll (не один застывший «feature extract + mapper»).
- **Синие «кубики» на Сцене (2026-09-04):** это sparse COLMAP (`THREE.Points` + disc sprites; размер уменьшен для плотных облаков), **не** фотореализм. Статус-бар: **`sparse COLMAP · нужен train для splat`** — ожидаемо после «Построить 3D», не ошибка. Фотореализм — после **Balanced/High** gsplat (`model.ply`). Bootstrap = минимальный splat, тоже не фотореализм. Idle-карточка на canvas объясняет pipeline и ведёт на Balanced. Модалка прогресса видна только во время COLMAP/train (после успеха закрывается).
- **DropInViewer placeholder bbox `[2,2,2]` (RESOLVED 2026-09-04):** после `addSplatScene` Three.js иногда даёт фиктивный unit box. UI **не** dispose’ит splat и не откатывается на Points; кадрирует по Points/sparse и позже re-frame; `sceneKind=splat` когда DropIn ready. Ранее retry dispose оставлял пользователя на sparse при живом `model.ply`. Placeholder **не** пишется в `sceneError` (иначе ops modal → «Повторить»). Effect deps без `sparsePoints.length` — иначе async sparse cancel’ил загрузку splat.
- **Ops modal idle (2026-09-04):** после `colmap_done` модалка исчезает — это нормально; смотрите карточку «Sparse COLMAP… → Balanced» на canvas, не считайте сцену «пустой». Тестируйте UI через Vite (`:3000`), не stale `dist`.
- **CSP / debug ingest `:7307` (2026-09-04):** debug-fetch снят из исходников; `connect-src` в `index.html` без `:7307`. Если консоль всё ещё ругается на `127.0.0.1:7307/ingest` — **hard-refresh** (`Ctrl+Shift+R`): устаревший Vite HMR-модуль `Flight3D.tsx?t=…`.
- **COLMAP sidecar auto-detect (2026-09-03):** если `COLMAP_ROOT` не задан, `recon_scanner._colmap_bin()` ищет `sidecars/colmap` (`COLMAP.bat`, `bin/colmap.exe`). Launchers (`npm run backend`, `start-backend.bat`, `Запустить.bat`, `desktop_launcher.py`) выставляют `COLMAP_ROOT` по умолчанию.
- **COLMAP exhaustive on drone video (RESOLVED 2026-09-04):** UI показывал `COLMAP failed:` + хвост glog **INFO** (`IYYYYMMDD… Exhaustive feature matching`) — это не текст ошибки, а обрыв matcher (часто GPU OOM на O(n²)). Fix: video frames → **sequential_matcher** (overlap env); frame/image size budget; GPU→CPU retry once; `format_colmap_error` без INFO-дампов; RU-хинт при слабой регистрации. Job `9844b6ace297` — нет `points3D` (убит на matching) → **не salvage**, нужен повтор Build 3D. См. [RECON_3D.md](RECON_3D.md).
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
