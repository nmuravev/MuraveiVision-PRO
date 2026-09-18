# CHANGELOG — MuraveiVision PRO

All notable changes to this project will be documented in this file.

## [v3.2.0] — 2026-09-19 — Bug Fix Audit v2.0 + DA3 Dense Backend

### Major New Feature: Depth Anything 3 (DA3) Dense Reconstruction

- **DA3 Dense Backend (all 4 variants):** `da3_dense_base` / `large` / `metric` / `giant`
  - **base** (Apache-2.0): Default, works on 8+ GB VRAM
  - **large** (CC BY-NC 4.0): Higher quality, needs 12+ GB VRAM
  - **metric** (Apache-2.0): Metric-scale reconstruction
  - **giant** (CC BY-NC 4.0): Highest quality, requires ≥16 GB VRAM (gated)
- **Sidecar-only deployment:** Weights in `sidecars/da3/`, never in `assets/models/`
- **Soft-fail recovery:** Preserves sparse cloud on <8 COLMAP views
- **Fail-closed:** `DA3_RUNTIME_UNAVAILABLE` when model can't load
- **NOTICE files:** CC BY-NC 4.0 license for large/giant variants
- **Pipeline integration:** Preset hierarchy Sparse → Dense (DA3) → Mesh (AV) → Splat
- **Binary PLY:** 6 fields xyzrgb, no normals
- **Config paths:** HF `config_*.json` + `inference()` path
- **Build machine:** `fetch_da3_weights.py` runs only on build machine during pack prep

### Sprint 3: P2 — Medium (15 fixes)

### Sprint 3: P2 — Medium (15 fixes)

| # | Fix | File | Description |
|---|-----|------|-------------|
| P2-15 | ffmpeg background | `backend/main.py` | Run ffmpeg subprocess in background thread to avoid blocking main loop |
| P2-5 | Missing key check | `backend/services/ai.py` | Guard against KeyError when AI class name field is missing |
| P2-7 | KeyError in export | `backend/services/recon.py` | Handle missing keys in reconstruction export pipeline |
| P2-1 | Catalog cache TTL | `backend/services/response_validator.py` | Add configurable TTL to class catalog cache to prevent stale data |
| P2-2 | vcvars64 caching | `backend/services/gsplat_msvc.py` | Persist vcvars64 cache to disk with PATH fallback for MSVC build |
| P2-3 | Lockout NAT support | `backend/api/auth.py` | Support NAT environments via client_key() for lockout mechanism |
| P2-6 | _sahi_default exceptions | `backend/api/detect.py` | Narrow exception handler scope to prevent masking real errors |
| P2-4 | Prompt injection | `backend/services/ai.py` | Wrap user prompts in DATA section to prevent injection attacks |
| P2-10 | useMemo tick removal | `MurVis/src/hooks/useReconOpsProgress.ts` | Remove `tick` from useMemo deps to reduce re-renders (~60x fewer) |
| P2-12 | waitScanIdle timeout | `MurVis/src/store/useBatchScanStore.ts` | Make 6000ms timeout configurable (SCAN_IDLE_TIMEOUT_MS), add explicit error state |
| P2-13 | Closure stale | `MurVis/src/hooks/useReconBuild.ts` | Replace `openSceneOnDone` parameter with useRef for last-write-wins behavior |
| P2-14 | Stale get() | `MurVis/src/store/useMuraveiStore.ts` | Move get() calls before async boundary to prevent stale state reads |
| P2-8 | Stale getState() | `MurVis/src/App.tsx` | Replace synchronous getState() in useEffect with Zustand selectors |
| P2-9 | WebSocket deps | `MurVis/src/components/panels/Viewer.tsx` | Stabilize WS deps via refs to prevent reconnect storms on state changes |
| P2-11 | Spread dedup | `MurVis/src/store/useViewerStore.ts` | Extract repeated spread pattern into ensureViewer() helper function |

### Sprint 2: P1 — High (14 fixes)

| # | Fix | File | Description |
|---|-----|------|-------------|
| P1-1 | Remove /peek-pin | `backend/api/auth.py` | Remove plaintext PIN endpoint for security |
| P1-2 | Thread-safe DB | `backend/services/db.py` | Add _write_lock for thread-safe database writes |
| P1-3 | SQL injection whitelist | `backend/services/db.py` | Implement _DETECTION_COLUMNS whitelist (18 columns) to prevent SQL injection |
| P1-4 | ollama_proxy lock | `backend/services/ollama_proxy.py` | Add threading.RLock() for thread-safe Ollama proxy operations |
| P1-5 | kind validation | `backend/api/recon.py` | Validate recon kind against whitelist {splat, dense, mesh, sparse} |
| P1-6 | Filename sanitization | `backend/services/network_attachments.py` | Sanitize filenames with Path(filename).name + validation (8 MB cap, sha256-verify) |
| P1-7 | WS undefined engine | `backend/api/detect.py` | Safe initialization of WebSocket engine to prevent undefined errors |
| P1-8 | HUD mask bytes.copy() | `backend/api/detect.py` | Prevent source mutation with bytes.copy() for HUD masks |
| P1-9 | Path traversal ws_detect | `backend/api/detect.py` | Add _sanitize_viewer_id() to prevent path traversal attacks |
| P1-10 | Batch error handling | `backend/services/yolo_engine.py` | Per-box try/except to prevent single failure from stopping batch |
| P1-11 | SQLite WAL checkpoint | `backend/services/db.py` | Add PRAGMA wal_autocheckpoint=1000 for better WAL management |
| P1-12 | Token hash storage | `backend/api/auth.py` | Store SHA-256 hash in _active_tokens instead of plaintext tokens |
| P1-13 | Exception handling recon | `backend/services/recon_scanner.py` | Add finally block cleanup for reconstruction scanner |
| P1-14 | readSse parsing | `MurVis/src/lib/readSse.ts` | Character-by-character buffer parsing for SSE events |

### Sprint 1: P0 — Critical (11 fixes)

| # | Fix | File | Description |
|---|-----|------|-------------|
| P0-1 | SSE timeout | `backend/api/recon.py` | Configurable SSE timeout with heartbeat mechanism |
| P0-2 | Orphaned task | `backend/api/network.py` | Managed asyncio.create_task() lifecycle to prevent orphaned tasks |
| P0-3 | Atomic fail_count | `backend/services/db.py` | Atomic SQL + retry logic for authentication fail_count |
| P0-4 | Path traversal recon | `backend/services/recon_scanner.py` | Add Path.relative_to() validation for recon_asset endpoints |
| P0-5 | GPU memory leak | `backend/services/sam3_engine.py` | Tensor pool + periodic empty_cache() to prevent VRAM leaks |
| P0-6 | OOM fallback | `backend/services/yolo_engine.py` | Device restoration + retry on OutOfMemory errors |
| P0-7 | Stale running state | `backend/services/recon_scanner.py` | Heartbeat monitoring + cleanup for stale running recon jobs |
| P0-8 | Unsafe pickle RCE | `backend/services/catalog.py` | Replace pickle with msgpack + RestrictedUnpickler to prevent RCE |
| P0-9 | gsplat race condition | `backend/services/gsplat_msvc.py` | Add portalocker to prevent race conditions in gsplat training |
| P0-10 | Sam3Store cleanup | `MurVis/src/store/useSam3Store.ts` | Add cleanupAllIntervals() to prevent memory leaks |
| P0-11 | Batch stores cleanup | `MurVis/src/store/useBatchChangeStore.ts`, `useBatchSegStore.ts` | Apply same interval cleanup pattern as P0-10 |

---

### Security Fixes Summary

- **RCE Prevention:** Replaced unsafe pickle with msgpack (P0-8)
- **SQL Injection:** Column whitelist implementation (P1-3)
- **Path Traversal:** Validation in recon_asset and ws_detect (P0-4, P1-9)
- **Prompt Injection:** DATA section wrapping for AI prompts (P2-4)
- **Token Security:** SHA-256 hash storage instead of plaintext (P1-12)
- **Network Security:** JWT authentication for WebSocket endpoints

### Performance Improvements

- **Re-render Optimization:** ~60x fewer re-renders in useReconOpsProgress (P2-10)
- **WebSocket Stability:** Ref-based dependency stabilization prevents reconnect storms (P2-9)
- **GPU Memory:** Tensor pool management prevents VRAM leaks (P0-5)
- **Database:** WAL checkpoint optimization (P1-11)
- **Async Lifecycle:** Proper task management prevents orphaned operations (P0-2)

### Reliability Improvements

- **Air-Gap Ready:** All fixes designed for offline environments
- **Error Handling:** Comprehensive try/except blocks in batch operations (P1-10)
- **State Management:** Eliminated stale closure and get() issues (P2-8, P2-13, P2-14)
- **Timeout Handling:** Configurable timeouts with explicit error states (P0-1, P2-12)

---

## Testing

- **Backend unit tests:** 407+ tests (pre-commit gate)
- **Playwright E2E:** Field tests with VITE_MURAVEI_E2E=1 for air-gap
- **Smoke tests:** dual_network_smoke.py, verify_da3_weights.py, test_sahi_field.py
- **Portable smoke:** smoke_portable Mini + FullKit

## Migration Notes

- No database schema changes in v3.2.0
- No breaking API changes
- All changes are backward compatible
- DA3 weights require NOTICE file for CC BY-NC 4.0 variants (large, giant)
