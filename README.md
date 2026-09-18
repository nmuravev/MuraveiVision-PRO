# MuraveiVision PRO v3.2

Автономный тактический видеоанализ (YOLO) для Windows. Portable ZIP — без установки Node/Python на полевом ноутбуке.

**Non-commercial project:** MuraveiVision PRO is distributed as an open **non-commercial** project. CC BY-NC 4.0 DA3 weights (LARGE / GIANT) in FullKit are for non-commercial use only — see [`docs/ATTRIBUTION.md`](docs/ATTRIBUTION.md) and `sidecars/da3/NOTICE_CC-BY-NC-4.0.txt`.

**Latest release:** [v3.2.0](https://github.com/nmuravev/MuraveiVision-PRO/releases/tag/v3.2.0)  
**Документация:** [`docs/`](docs/README.md) — архитектура, API, обучение, portable, гайд оператора, roadmap.

## Что нового в v3.2.0

### Bug Fix Audit v2.0 (2026-09-18)

Выполнен объединённый план исправления 40 багов (11 P0 + 14 P1 + 15 P2 pending) с соблюдением air-gap ограничений.

**Sprint 1 — P0 Critical (11/11 ✅):**
- SSE timeout с конфигурируемым таймаутом и heartbeat
- Atomic fail_count с retry logic для brute-force защиты
- GPU memory pool для предотвращения утечек
- Migration pickle → msgpack + RestrictedUnpickler
- Path traversal fixes в recon и ws_detect
- Interval cleanup в Sam3Store и Batch stores

**Sprint 2 — P1 High (14/14 ✅):**
- Thread-safe DB с _write_lock
- SQL injection whitelist (18 колонок)
- Token hash storage (SHA-256)
- WAL checkpoint для SQLite
- Character-by-character SSE parsing
- Batch error handling с per-box try/except

**Sprint 3 — P2 Medium (0/15 ⏳):**
Ожидают выполнения в следующем спринте (~19 часов).

Подробнее: [`docs/MASTER_PLAN.md`](docs/MASTER_PLAN.md) § Bug Fix Audit v2.0

## Быстрый старт (Portable)

1. Распакуйте ZIP  
2. `Запустить.bat`  
3. Браузер → http://127.0.0.1:8000  

## PIN по умолчанию

| Роль | PIN | Возможности |
|------|-----|-------------|
| Оператор | `1234567` | детекция, правки, обучение, отчёты, REC |
| Инженер | `0000000` | + модели, телеметрия, сеть, смена PIN оператора |
| Мастер | `0987907` | + все PIN |

Подробнее: [docs/OPERATOR_GUIDE.md](docs/OPERATOR_GUIDE.md).

## Модель

Detect-веса (не `*-seg*` как train base):

- `assets/models/yolo26n-ft.pt` — приоритетный finetune  
- `assets/models/yolo26n.pt` / `best.pt`  
- опционально YOLOE в `runs/...` (нужен CLIP)

Классы UI: **238** — `military_classes.yaml`.  
См. [docs/DETECTION_AND_TRAINING.md](docs/DETECTION_AND_TRAINING.md).

## Разработка

Только Python **3.12.10** из `muravei_env`:

```bat
muravei_env\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
npm run dev
```

Полный гайд: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).  
Для ИИ-агентов: [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Требования

- Windows 10/11  
- NVIDIA + CUDA желательны (`torch+cu128`)  
- ≥ 8 GB RAM (VRAM 8 GB — уменьшать batch/imgsz)  
- Порт `8000`  
- Ollama (опционально) на `127.0.0.1:11434` для AI-анализа  

## Известные ограничения

- Portable Lite без встроенной Ollama (Full Kit — в [docs/ROADMAP.md](docs/ROADMAP.md))  
- Без весов YOLO → `offline`, пустые детекции  
- Legacy-файлы в `.backup/` не являются актуальной документацией  
