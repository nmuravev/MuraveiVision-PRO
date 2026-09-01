# PROJECT_CONTEXT — паспорт MuraveiVision PRO v3.0

Документ для ИИ-агентов и новых разработчиков. Описывает **текущий** репозиторий `d:\LLM\MuraveiVision-PRO`, не legacy из `.backup/`.

## 1. Назначение

Автономный (air-gapped) комплекс тактического видеоанализа на Windows:

- детекция военных объектов (Ultralytics YOLO26 / опционально YOLOE);
- архив и live (RTSP/UDP/HTTP);
- ручная правка bbox, фиксация кропов, дообучение;
- локальный ИИ-анализ через Ollama;
- portable ZIP без установки Node/Python на полевом ПК.

## 2. Стек (факт)

| Слой | Технологии |
|------|------------|
| Frontend | React 19, TypeScript, Vite, Tailwind, **react-mosaic-component**, Zustand |
| Backend | FastAPI, Uvicorn, aiosqlite/SQLite, PyJWT, bcrypt, httpx |
| Inference | Ultralytics ≥8.4.116, PyTorch (**нужен `torch+cu128` для GPU**), OpenCV |
| Analytics | Ollama на `127.0.0.1:11434` (прокси только через backend) |
| Desktop (опц.) | pywebview через `backend/desktop_launcher.py` |
| Python | **Только** `muravei_env\Scripts\python.exe` → **3.12.10** |

Системный Python 3.14 на машине сборки **запрещён** (см. `.cursor/rules/muravei-python-env.mdc`).

## 3. Топография (сокращённо)

```
MuraveiVision-PRO/
├── backend/                 # FastAPI app (main.py), api/, services/, scripts/
├── src/                     # React UI (App.tsx + mosaic panels)
├── dist/                    # production UI (npm run build)
├── assets/models/           # detect .pt (yolo26n.pt, yolo26n-ft.pt, best.pt)
├── runs/detect/train/weights/
├── archive/                 # медиа, crops/, recordings/, .trash/
├── cache/                   # train runs, finetune datasets
├── logs/                    # train/smoke/ai logs
├── muravei_env/             # Python 3.12.10 venv
├── military_classes.yaml    # 238 UI/model class names
├── docs/                    # эта документация
├── scripts/build_portable.ps1
├── Запустить.bat
└── package.json
```

Полное дерево: [DIRECTORY_STRUCTURE.md](DIRECTORY_STRUCTURE.md).

## 4. Роли и PIN (по умолчанию)

| Роль | PIN | Права |
|------|-----|--------|
| Оператор | `1234567` | детекция, правки, обучение, отчёты, REC |
| Инженер | `0000000` | + модели, телеметрия, сеть, смена PIN оператора |
| Мастер | `0987907` | + все PIN, factory-уровень |

JWT, блокировка после 5 неудачных попыток. Хеши в SQLite (`muravei.db`).

## 5. UI-режимы (TopBar)

Не Mini/Pro legacy. Рабочие пресеты mosaic:

- **Медиа** — MediaPool + Viewer + Timeline  
- **Монтаж** — MediaPool, Viewer×2, Inspector, Timeline, Queue  
- **AI-анализ** — AiAnalysisPanel + Viewer + Inspector  
- **Обучение** — UpdatePanel + Viewer  
- **Система** — AdminPanel + NetworkPanel (+ словарь классов)

Панели: `src/components/panels/*`, реестр в `ComponentRegistry.tsx`.

## 6. Модель и классы

- Каталог UI: **238** имён в `military_classes.yaml` (`backend/services/classes.py`).
- Активный detect-вес после finetune: `assets/models/yolo26n-ft.pt` (приоритет загрузки выше YOLOE, если файл есть).
- YOLOE (`yoloe-*-seg.pt`) — open-vocab, нужен CLIP/`mobileclip2_b.ts`.
- COCO `yolo26n.pt` — fallback только если primary пустой.
- Import rule: `nc ∈ {12, 238}` (`model_validator.py`).

## 7. Запуск (разработка)

```powershell
# Backend
.\muravei_env\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000

# Frontend
npm run dev
```

Или `npm run backend` / `npm run desktop`. Поле: `Запустить.bat` из Portable.

## 8. Жёсткие правила для ИИ

1. Не вызывать bare `python` / `pip` — только `muravei_env`.
2. Frontend → backend только **относительными** путями `/api/...` (не хардкод чужих IP; локальный origin ок).
3. Не тащить cloud API; Ollama только localhost через `services/ollama_proxy.py`.
4. Detect-train — **не** seg/YOLOE как base (`trainer.py`).
5. Не коммитить секреты, `.env` с PIN, огромные веса/датасеты без запроса.
6. Документация проекта живёт в `docs/`; не восстанавливать устаревший `.backup` CONTEXT как истину.

## 9. Связанные документы

- [ARCHITECTURE_FOR_AI.md](ARCHITECTURE_FOR_AI.md)  
- [API.md](API.md)  
- [DETECTION_AND_TRAINING.md](DETECTION_AND_TRAINING.md)  
- [DEVELOPMENT.md](DEVELOPMENT.md)
