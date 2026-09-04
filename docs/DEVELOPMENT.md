# Разработка

## Обязательное окружение

- OS: Windows 10/11  
- Node.js для Vite  
- Только `muravei_env\Scripts\python.exe` (**3.12.10**)  
- GPU: NVIDIA + драйвер; PyTorch cu128 для CUDA

Правило Cursor: `.cursor/rules/muravei-python-env.mdc`.

## Установка зависимостей

```powershell
# Python
.\muravei_env\Scripts\pip.exe install --no-cache-dir -r backend\requirements.txt
# GPU torch (если ещё CPU-only)
.\muravei_env\Scripts\pip.exe install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu128

# Frontend
npm install
```

Проверка:

```powershell
.\muravei_env\Scripts\python.exe -c "import sys; print(sys.version)"
.\muravei_env\Scripts\pip.exe check
```

## Запуск

```powershell
# терминал 1
npm run backend
# терминал 2
npm run dev
```

Desktop shell: `npm run desktop`.

Порт API: **8000**.

## Полезные npm scripts

| Script | Действие |
|--------|----------|
| `backend` | uvicorn **без** `--reload` (безопасно для COLMAP/gsplat train) |
| `backend:watch` | uvicorn с `--reload` (только UI/API dev; **не** во время train) |
| `backend:install` | pip requirements |
| `desktop` | pywebview launcher |
| `smoke:phase3` / `smoke:phase4` | регрессии API |
| `portable` | `build_portable.ps1 -FetchEmbeddablePython` |
| `build` | `tsc && vite build` → `dist/` |

## Стиль правок

- Минимальный diff, без лишних markdown вне `docs/`.  
- Не трогать `openreel-reference/` без задачи.  
- Не коммитить веса/датасеты/`.backup` огромные файлы без запроса.  
- Git commit — только по явной просьбе пользователя.

## Отладка

- `DebugPanel` — логи UI + статус YOLO.  
- `logs/ai.log`, `logs/train.log`, `logs/backup_finetune_cuda.log`.  
- `GET /api/detect/status`, `GET /api/system/hardware`.

## Типичные ловушки

1. `torch 2.x+cpu` → обучение на CPU часами / `cuda False`.  
2. OOM 8 GB при imgsz=1024 batch=16 → уменьшить imgsz/batch, `empty_cache`.  
3. После train UI показывает YOLOE — нужен `force_load` ft (исправлено в engine priority).  
4. Circular import в скриптах: сначала `importlib.import_module("main")`.
