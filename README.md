# MuraveiVision PRO v3.0

Автономный тактический видеоанализ (YOLO) для Windows. Portable ZIP — без установки Node/Python на полевом ноутбуке.

**Документация:** [`docs/`](docs/README.md) — архитектура, API, обучение, portable, гайд оператора, roadmap.

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
Для ИИ-агентов: [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md), [docs/ARCHITECTURE_FOR_AI.md](docs/ARCHITECTURE_FOR_AI.md).

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
