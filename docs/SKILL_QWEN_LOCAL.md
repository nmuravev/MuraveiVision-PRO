# MuraveiVision PRO — Local Qwen 2.5-coder 7b Onboarding Skill

> **Прочитай этот файл ПЕРВЫМ перед любым изучением кода.**

## Контекст исполнения

Continue.dev + `qwen2.5-coder:7b` через локальный Ollama.

- RAM/VRAM ограничены — не раздувай контекст
- Контекст: держи ≤16k токенов
- Не читай репо целиком; используй явные `@file` / `@folder`
- Избегай `@codebase` без необходимости (OOM)
- Длинный вывод команд → `logs/`, читай хвост

## Архитектура

Автономная платформа инспекции и съёмки: видео с аэроплатформ → распознавание объектов → треки → 3D → peer sync.

### Стек
Python 3.12 + FastAPI; Vite/React/TS; YOLO26 + SAM3 + SAHI + ORT; COLMAP/AliceVision/gsplat; portable ZIP.

### Запуск
`Запустить.bat` → env air-gap → `python -m uvicorn main:app --app-dir backend`.
Первый импорт: `ensure_ultralytics_airgap` из `backend/services/ultralytics_airgap.py`.

## Жёсткие политики

1. Z1 zero-hardcode
2. Air-gap runtime (нет pip/uv из backend)
3. Логи только в `logs/`
4. Pack hygiene (см. PORTABLE_GUIDE)
5. GitHub = changelog only
6. v3.3 lock RETIRED (2026-09-16) — scope in main via N1–N6; no long-lived locks

## Карта файлов

| Область | Путь |
|---------|------|
| Airgap | `backend/services/ultralytics_airgap.py` (`ensure_ultralytics_airgap`) |
| YOLO/SAM3/ffmpeg | `backend/services/yolo_engine.py`, `sam3_engine.py`, `ffmpeg_util.py` |
| CI | `scripts/ci_full.ps1` |
| Smoke/build | `scripts/smoke_portable.ps1`, `build_portable.ps1` |
| Manifest | `scripts/portable_manifest.json` |

## Как начать задачу

1. `docs/MASTER_PLAN.md` Meta
2. `docs/TODO.md`
3. Z1 / air-gap / hygiene
4. `scripts/ci_full.ps1` перед коммитом
5. Conventional commits

## Антипаттерны

- ❌ pip в backend · абсолютные пути · Ollama в паке · COCO downloads · бинари на GitHub · `@codebase` без нужды
