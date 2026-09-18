# Roadmap (P0–P3)

> **Master Plan:** See [`MASTER_PLAN.md`](MASTER_PLAN.md) for comprehensive overview (status, invariants, backlog, docs auto-sync).

Согласованное направление: реализовать весь бэклог поэтапно. Этот файл отражает фактический статус исходников; рабочие планы Cursor не являются документацией продукта.

## Уже сделано (база)

- Mosaic UI, детекция YOLO26/YOLOE, live, tracker/motion  
- 238 классов, словарь overrides  
- Quick train + backup finetune CUDA → `yolo26n-ft.pt`  
- Ollama proxy, HTML-отчёт, portable Lite  
- Force-load ft, smoke LBS
- **v3.2 recon (historical branch name):** COLMAP multi-model best sparse + AliceVision Mesh-only opt-in already on **main** via DA3/P8 era (`alicevision_enabled`); Dense = DA3. Branch `feature/alicevision-v3.2` is not a pending merge target. См. [ALICEVISION.md](ALICEVISION.md), [RECON_3D.md](RECON_3D.md).
- **v3.4 DA3 Dense Backend (DONE on main):** all-variants `da3_dense_base` / `large` / `metric` / `giant` (≥16 GB gate); NC NOTICE; Dense=DA3 default; AliceVision Mesh-only opt-in (`alicevision_enabled`). See [RECON_3D.md](RECON_3D.md), [ALICEVISION.md](ALICEVISION.md).
- **v3.3 network realtime (UNLOCKED 2026-09-16):** lock on `feature/network-chat-v3.3` **retired** (branch deleted; zero unique commits). Scope lands in main via short phases N1–N6 (WS chat, attachments, refs, package share, LAN beacon). No long-lived locked branches.

## P0 — операторский конвейер

1. Batch-скан архивного видео → маркеры timeline / auto-commit — **сделано**  
2. Rules & alerts (класс+conf → звук + галерея) — **сделано**  
3. Active learning: low-confidence → confirm/false-positive → train — **сделано**  
4. Гео v1: sidecar SRT/CSV → `gps_*` на детекциях / отчёт — **сделано**  

## Гео 3D (после P0.4)

- Отдельная mosaic-панель **Flight3D** (three.js) — **сделано (Sprint B.1)**  
- Траектория `{t,lat,lon,alt}` + синхрон с Viewer  
- **Не** OCR OSD в первой версии (ненадёжно)

Сложность: средняя при наличии SRT; высокая при OCR-only.

## P1 — модель и разметка

5. Ollama-assisted autolabel на 238 (confirm UI) — **сделано**  
6. Find-similar (CLIP image + hist fallback, кэш векторов) — **сделано**  
7. Per-class conf в словаре — **сделано**  
8. Resume train UI (imgsz/batch/VRAM, last.pt) — **сделано**  

## Portable Full Kit (связка с п.5)

**Сделано (Sprint B.2):** флаг `-FullKit` в [`scripts/build_portable.ps1`](../scripts/build_portable.ps1) / `npm run portable:full`.

В ZIP без полевого download:

- `ollama` windows + модель **`qwen2.5vl:7b`** (~6 GB)  
- `yolo26n-ft.pt`, `mobileclip2_b.ts` (если есть)  
- torch **cu128** в embeddable env (`muravei_env` 3.12.10)  
- `Запустить.bat` поднимает Ollama → API → браузер  

Ожидаемый размер Full: ~12–18 GB. Lite остаётся тонким комплектом.

## P2 — сеть и продукт

9. Реальная репликация целей между базами — **DONE** (3.1, worker + JWT + `?since=`)  
10. Пресет 4×Live + event timeline — **DONE** (3.2)  
11. KML/GeoJSON + PDF — **DONE** (Stage 1 / 3.3)  
12. Hotkeys оператора — **DONE** (Stage 1 / 3.4)  

## P3 — DONE (segmentation + change detection + field UX)

13. Seg-маски (P3.13 v1.1) — **DONE** (`ea881fc`): archive-only, load/unload VRAM, кнопка кадра, полигоны SVG. Не в `/ws/detect`, не в 4×Live, не в train.  
13b. Batch segmentation (P3.13.2) — **DONE** (`2f7a86c`): `POST /api/seg/batch`, modal, frame_step, in-memory results + seek.  
13c. SAM3 interactive refine (P3.13.3a) — **DONE** (`8baa39f`): `sam3.pt`, point/bbox, mutual VRAM YOLO-seg.  
13d. SAM3 short propagate (P3.13.3b) — **DONE** (`b533f0d`): ≤30 fwd, temp clip, opt-in `seg_masks`.  
13e. SAM3 text + Live freeze (P3.13.3c) — **DONE**: `SAM3SemanticPredictor` / text XOR visual; Live JPEG-capture overlay без unload Detect.  
14. Change Detection (P3.15 v1) — **DONE** (`a798b15`): Compare Sync, GPS-matching + ORB fallback, Inspector, цветные bbox.  
14b. Auto Time Sync (P3.15.2) — **DONE** (`8279f8f`): GPS tracks → detections fallback → сегменты, CompareSyncModal.  
14c. HTML/KML Export (P3.15.3) — **DONE** (`8f93bb1`): `GET /export`, Inspector кнопки, `change_export` / `build_change_kml`.  
14d. Diff Heatmap (P3.15.4) — **DONE** (`8b2ff99`): `image_diff.heatmap_b64` + Viewer «Теплокарта».  
14e. Batch Change Detection (P3.15.5) — **DONE**: subsample `auto_sync` pairs → `analyze_pair`, aggregate unique IDs, HTML export.
15. Audio cue по bbox — **DONE** (RulesPanel: beep/alarm/none)  
16. USB offline model manager — **DONE** (4.1, scan + validate + confirm + force_load)  

Инфраструктура сессии: Playwright E2E (`4aa75af`), error catalog (`7a30f1d`).

## B1–B3 (v3.5 backlog — DONE)

- **B1. Perf table** — **DONE** (`848ae44`): ms/VRAM budget table @ 8GB in CONFIGURATION.md + KNOWN_ISSUES.md
- **B2. Mask export** — **DONE** (`c908d01`): GeoTIFF (rasterio) + KML masks with GPS gate; 14 unit tests
- **B3. Full-video SAM3 propagate** — **DONE** (`<COMMIT_HASH>`): chunked windows ≤30, stride=25, overlap=5, dedup, VRAM guard, abort per-frame/chunk, OOM handling, persist to SQLite

Ретроспектива: [PHASE3_FINAL_RETRO.md](PHASE3_FINAL_RETRO.md). Sprint notes: [PHASE4_RETRO.md](PHASE4_RETRO.md).

## Bug Fix Audit v2.0 (2026-09-18)

Unified 40-bug fix plan executed with strict air-gap constraints. 26 commits in remote (30ff7f1..7c49b76).

### Sprint 1: P0 — Critical (11/11 ✅)

- P0-1: SSE Stream Never Terminates → configurable timeout + heartbeat
- P0-2: Orphaned asyncio.create_task() → managed task lifecycle
- P0-3: Non-atomic fail_count → atomic SQL + retry logic
- P0-4: Path traversal in recon_asset → relative_to() validation
- P0-5: GPU Memory Leak → tensor pool + periodic empty_cache()
- P0-6: OOM Fallback recovery → device restoration + retry
- P0-7: Stale Running State → heartbeat monitoring + cleanup
- P0-8: Unsafe Pickle RCE → msgpack + RestrictedUnpickler
- P0-9: Race Condition gsplat → portalocker
- P0-10: Sam3Store interval cleanup → cleanupAllIntervals()
- P0-11: Batch stores interval cleanup → аналогичный паттерн

### Sprint 2: P1 — High (14/14 ✅)

- P1-1: Plaintext PIN /peek-pin → endpoint removed
- P1-2: Thread-safe DB → _write_lock для записи
- P1-3: SQL injection → _DETECTION_COLUMNS whitelist (18 колонок)
- P1-4: ollama_proxy lock → threading.RLock()
- P1-5: kind validation → whitelist {"splat", "dense", "mesh", "sparse"}
- P1-6: Filename sanitization → Path(filename).name + validation
- P1-7: WS undefined engine → safe engine initialization
- P1-8: HUD mask bytes.copy() → prevent source mutation
- P1-9: Path traversal ws_detect → _sanitize_viewer_id()
- P1-10: Batch error handling → per-box try/except
- P1-11: SQLite WAL checkpoint → PRAGMA wal_autocheckpoint=1000
- P1-12: Token hash storage → SHA-256 hash in _active_tokens
- P1-13: Exception handling → finally block cleanup
- P1-14: readSse fix → character-by-character buffer parsing

### Sprint 3: P2 — Medium (0/15 ⏳)

Ожидают выполнения (~19 часов):
- P2-1: Catalog cache TTL (response_validator.py)
- P2-2: vcvars64 caching (gsplat_msvc.py)
- P2-3: Lockout NAT support (auth.py)
- P2-4: Prompt sanitization (ai.py)
- P2-5: Missing key check (ai.py)
- P2-6: _sahi_default exceptions (detect.py)
- P2-7: KeyError in export (recon.py)
- P2-8: App.tsx stale state (App.tsx)
- P2-9: WebSocket deps (Viewer.tsx)
- P2-10: useMemo tick (useReconOpsProgress.ts)
- P2-11: ViewerStore Immer (useViewerStore.ts)
- P2-12: waitScanIdle deadline (useBatchScanStore.ts)
- P2-13: Closure stale (useReconBuild.ts)
- P2-14: hydrateDetections get() (useMuraveiStore.ts)
- P2-15: ffmpeg background (main.py)

### Pre-Sprint Tasks

- M0: Data Migration — ⏳ НЕ НАЧАТО
- T1: Load Testing — ⏳ НЕ НАЧАТО
- Wheels download — ⏳ НЕ ВЫПОЛНЕНО

## Future / Backlog

| # | ID | Задача | Приоритет | Заметки |
|---|-----|--------|-----------|---------|
| 1 | Perf | Profiling batch seg / propagate / dual-viewer на edge GPU | P2 | Полевой smoke + метрики ms/VRAM |
| 2 | Export | GeoTIFF/KML масок batch/propagate | по запросу | Не блокирует Phase 3 |
| 3 | AV | AliceVision Mesh-only already on main (`alicevision_enabled`); no separate v3.2 branch merge | done | Dense = DA3 |
| 4 | Audit | Bug Fix Audit v2.0 — P0(11/11)✅ P1(14/14)✅ P2(0/15)⏳ | DONE | 26 коммитов в remote |
| 5 | — | Новые фичи | по запросу пользователя | Placeholder |

Чеклисты: [TODO.md](TODO.md).

## Вне скоупа

Облако, SaaS, полноценный NLE-монтаж.
