# Архитектура MuraveiVision PRO

## Обзор

Локальный монолит: браузерный (или pywebview) UI ↔ FastAPI на `127.0.0.1:8000` ↔ GPU/CPU инференс + SQLite + опционально Ollama.

## Слои

### Presentation

- `src/App.tsx` — mosaic layout, режимы TopBar.
- Панели в `src/components/panels/`.
- Состояние: `src/store/useMuraveiStore.ts`, `usePanelLayoutStore.ts` (persist layout).
- Тема: тёмный DaVinci-подобный chrome (плоские панели, акценты playhead).

### Application API

Роутеры `backend/api/*`, подключаются из `backend/main.py`.

Основные группы:

- auth, media, detect (+ WS), detections, train/export, ai, live, rec, reports, models, system, network, classes, queue, support.

### Domain services

| Сервис | Роль |
|--------|------|
| `yolo_engine.py` | загрузка весов, predict, tile/NMS, device tier |
| `tracker.py` / `motion.py` | track_id, vx/vy, ego-motion |
| `trainer.py` | quick finetune + SSE |
| `classes.py` | 238 YAML + overrides |
| `similarity.py` | hist+class find-similar (air-gap) |
| `ollama_proxy.py` | tags/generate, ranking vision/chat |
| `live_stream.py` / `recorder.py` | RTSP/UDP + REC |
| `reporter.py` | автономный HTML-отчёт |
| `db.py` | detections, crops, auth, network, overrides |

### Data

- `muravei.db` — оперативные данные.
- `archive/` — исходные медиа и артефакты.
- `assets/models/` — веса detect.
- `cache/` — временные train/scan датасеты.
- `logs/` — диагностика.

## Потоки данных

### Live / Viewer frame

```
Viewer JPEG → WS /ws/detect/{viewer_id}
  → yolo_engine.infer
  → tracker + motion
  → overlay JSON (objects, tracks, ego, ms)
```

### Фиксация

```
Commit detections → POST /api/detections/commit
  → crops JPEG + SQLite rows
  → BattleGallery / train dataset
```

### Дообучение

```
UpdatePanel → POST /api/train/start
  → trainer builds YOLO dataset from crops
  → ultralytics.train(device=cuda|cpu)
  → promote yolo26n-ft.pt → force_load
```

### AI analysis

```
AiAnalysisPanel / Inspector → POST /api/ai/analyze
  → ollama_proxy → localhost:11434
```

## UI mosaic

Листья (leaf ids) регистрируются в `ComponentRegistry`. Оператор перетаскивает панели, сохраняет layout в localStorage. Пресеты TopBar меняют дерево целиком.

Viewer поддерживает до 4 инстансов, Архив|Live, pan/zoom, bbox edit, REC, compare Было/Стало.

## Безопасность

- JWT после PIN.
- Relative `/api` пути.
- Ограничение FS к `archive/`.
- Portable CSP meta в `dist/index.html`.

## Что не является частью текущего PRO

- Отдельная папка `models/*.onnx` как единственный runtime (legacy backup).
- Режимы MiniMode / Workspace 4×4 из старого PROJECT_CONTEXT.
- Облачные LLM.
