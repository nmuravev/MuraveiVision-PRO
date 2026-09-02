# Roadmap (P0–P3)

Согласованное направление: реализовать весь бэклог поэтапно. Этот файл отражает фактический статус исходников; рабочие планы Cursor не являются документацией продукта.

## Уже сделано (база)

- Mosaic UI, детекция YOLO26/YOLOE, live, tracker/motion  
- 238 классов, словарь overrides  
- Quick train + backup finetune CUDA → `yolo26n-ft.pt`  
- Ollama proxy, HTML-отчёт, portable Lite  
- Force-load ft, smoke LBS

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

## P3 — DONE (v1 + v2 core)

13. Seg-маски (P3.13 v1.1) — **DONE** (`ea881fc`): archive-only, load/unload VRAM, кнопка кадра, полигоны SVG. Не в `/ws/detect`, не в 4×Live, не в train.  
14. Change Detection (P3.15 v1) — **DONE** (`a798b15`): Compare Sync, GPS-matching + ORB fallback, Inspector, цветные bbox.  
14b. Auto Time Sync (P3.15.2) — **DONE** (`8279f8f`): GPS tracks → detections fallback → сегменты, CompareSyncModal.  
14c. HTML/KML Export (P3.15.3) — **DONE** (`8f93bb1`): `GET /export`, Inspector кнопки, `change_export` / `build_change_kml`.  
15. Audio cue по bbox — **DONE** (RulesPanel: beep/alarm/none)  
16. USB offline model manager — **DONE** (4.1, scan + validate + confirm + force_load)  

Ретроспектива: [PHASE4_RETRO.md](PHASE4_RETRO.md) (Sprint 1 + Sprint 2).

## Next Sprint / Backlog

| # | ID | Задача | Приоритет |
|---|-----|--------|-----------|
| 1 | E2E | Playwright: seg toggle + change analyze UI | P0 |
| 2 | P3.15.4 | Diff heatmap canvas overlay | P1 |
| 3 | P3.13.2 | Batch-сегментация ролика | P1 |
| 4 | P3.13.3 | SAM2 (если модель) | P2 |

Чеклисты: [TODO.md](TODO.md). Детали Sprint 2: [PHASE4_RETRO.md](PHASE4_RETRO.md#sprint-2-p315-v2-completion).

## Вне скоупа

Облако, SaaS, полноценный NLE-монтаж.
