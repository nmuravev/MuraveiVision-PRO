# Smoke Test Results — video_2026-08-25_09-17-15.mp4

Date: 2026-09-02  
Method: **Playwright ephemeral** (`tests/smoke_real_video.test.ts`, deleted after run — not committed)  
File: `archive/video_2026-08-25_09-17-15.mp4` (~202 MB)  
Resolved: `1280×774`, duration **543.3 s**, H.264  
Source path used: `D:/LLM/MuraveiVision-PRO/archive/video_2026-08-25_09-17-15.mp4`

## Honesty note

- Steps marked **PASS (UI + mock)** used mocked SAM3/CD/export APIs. They validate UI wiring, not GPU mask quality or VRAM.
- Steps marked **PASS (real)** hit live media/detect paths against this file.
- This is **not** a full 8 GB field GPU profile for SAM3 load.

## Results

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | Media Pool | PASS (real) | `GET /api/media/tree` lists file. Media-row `data-media-path` not visible in default tree UI (`visible=false`); source set via store. |
| 2 | Viewer archive | PASS (real) | Video loads `readyState=4`, seek/play/pause OK. |
| 3 | Detect (YOLO) | PASS (real) | After play, **24** SVG labels with `%` confidence. Screenshot: `test-results/smoke_real_video/01_detect.png` (gitignored). |
| 4 | Segmentation (YOLO-seg) | SKIP | `yolo26n-seg.pt` missing in `assets/models/`. |
| 5 | Batch segmentation | SKIP | Same — no seg weights. |
| 6 | SAM3 interactive (point) | FAIL | Point/tool click did not produce SVG polygon within 12s (likely React `paused` / pointer path). **Not fixed in this task.** Text path (#7) did render mocked mask. |
| 7 | SAM3 text | PASS (UI + mock) | «По тексту» + mocked `/api/seg/sam3/infer` → mask. |
| 8 | SAM3 propagate | PASS (UI + mock) | Modal + mocked propagate job summary. |
| 9 | SAM3 Live freeze | N/A | No RTSP in this automation. |
| 10 | Change Detection | PASS (UI + mock) | Монтаж + Было/Стало + mocked analyze. Screenshot: `03_cd_inspector.png`. |
| 11 | Auto Time Sync | N/A | No SRT/CSV sidecar for this basename. |
| 12 | Analyze changes | PASS (UI + mock) | Inspector shows new `truck` / removed `car`. |
| 13 | Diff Heatmap | N/A | Mock analyze had no `heatmap_b64`. |
| 14 | Export HTML/KML | PASS (UI + mock) | «Экспорт HTML» clicked (mock body). KML disabled (no GPS in mock) — expected. |

## Issues Found

1. **SAM3 point tool (#6)** — UI click path did not yield a polygon on this run while text infer did. Repro: SEG → Точка → click canvas after detect session. Separate ticket; do not mix with docs-only smoke.
2. **Media Pool tree row** — basename present in API tree but not shown as `data-media-path` row without expanding/list mode in this layout. Workaround: `setSource` via store (acceptable for smoke).
3. **Missing `yolo26n-seg.pt`** — SEG + batch SKIP until weights are placed under `assets/models/`.
4. **No telemetry sidecar** — GPS sync / KML GPS remain N/A for this file.

## VRAM Usage

Automated run used **mocked** SAM3/CD infer — no meaningful SAM3 VRAM sample.

Idle/detect-ish sample during session (`nvidia-smi`): **~551 MiB / 8151 MiB** (not a peak under real `sam3.pt` load).

For a real 8 GB profile: manual load SAM3 + Detect without mocks (out of scope here).

## Artifacts (local, gitignored)

- `test-results/smoke_real_video/results.json`
- `test-results/smoke_real_video/01_detect.png`
- `test-results/smoke_real_video/03_cd_inspector.png`
- `02_sam3_mask.png` may be absent due to #6 FAIL

## Git hygiene

- Ephemeral Playwright file **deleted** after run (not committed).
- Video / `*.pt` **not** staged (covered by `.gitignore`: `archive/`, `*.mp4`, `assets/models/*.pt`).
- Production code **unchanged** by this task.
