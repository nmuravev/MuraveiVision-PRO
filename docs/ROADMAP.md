# Roadmap (P0–P3)

Согласованное направление: реализовать весь бэклог поэтапно. Этот файл отражает фактический статус исходников; рабочие планы Cursor не являются документацией продукта.

## Уже сделано (база)

- Mosaic UI, детекция YOLO26/YOLOE, live, tracker/motion  
- 238 классов, словарь overrides  
- Quick train + backup finetune CUDA → `yolo26n-ft.pt`  
- Ollama proxy, HTML-отчёт, portable Lite  
- Force-load ft, smoke LBS

## P0 — операторский конвейер

1. Batch-скан архивного видео → маркеры timeline / auto-commit  
2. Rules & alerts (класс+conf → звук + галерея) — **сделано**  
3. Active learning: low-confidence → confirm/false-positive → train — **сделано**  
4. Гео v1: sidecar SRT/CSV → `gps_*` на детекциях / отчёт  

## Гео 3D (после P0.4)

- Отдельная mosaic-панель **Flight3D** (three.js) — **сделано (Sprint B.1)**  
- Траектория `{t,lat,lon,alt}` + синхрон с Viewer  
- **Не** OCR OSD в первой версии (ненадёжно)

Сложность: средняя при наличии SRT; высокая при OCR-only.

## P1 — модель и разметка

5. Ollama-assisted autolabel на 238 (confirm UI) — **сделано**  
6. Find-similar на mobileclip  
7. Per-class conf в словаре — **сделано**  
8. Resume train UI (imgsz/batch/VRAM)

## Portable Full Kit (связка с п.5)

**Сделано (Sprint B.2):** флаг `-FullKit` в [`scripts/build_portable.ps1`](../scripts/build_portable.ps1) / `npm run portable:full`.

В ZIP без полевого download:

- `ollama` windows + модель **`qwen2.5vl:7b`** (~6 GB)  
- `yolo26n-ft.pt`, `mobileclip2_b.ts` (если есть)  
- torch **cu128** в embeddable env (`muravei_env` 3.12.10)  
- `Запустить.bat` поднимает Ollama → API → браузер  

Ожидаемый размер Full: ~12–18 GB. Lite остаётся тонким комплектом.

## P2 — сеть и продукт

9. Реальная репликация целей между базами  
10. Пресет 4×Live + event timeline  
11. KML/GeoJSON + PDF  
12. Hotkeys оператора  

## P3

13. Seg-маски укреплений (осторожно с detect-train)  
14. Audio cue по bbox  
15. Change detection двух пролётов  
16. USB offline model manager  

## Вне скоупа

Облако, SaaS, полноценный NLE-монтаж.
