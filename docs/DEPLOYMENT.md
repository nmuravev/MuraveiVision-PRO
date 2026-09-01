# Развёртывание

Развёртывание с нуля на Windows. Python — строго 3.12.10 через `muravei_env` (см. [.cursor/rules/muravei-python-env.mdc](../.cursor/rules/muravei-python-env.mdc)).

## Предусловия

- Windows 10/11 x64.
- Node.js 18+ (для фронта).
- ffmpeg на PATH (запись, transcode, filmstrip).
- (Опц.) CUDA-видеокарта NVIDIA — для GPU-инференса YOLO. Без неё — CPU.
- (Опц.) [Ollama](https://ollama.com) — для AI-аналитики/autolabel. Без неё — функции недоступны, остальное работает.
- (Опц.) COLMAP + gsplat — для фотограмметрии. Без них 3D-реконструкция недоступна.

## Из исходников

```powershell
git clone <repo> MuraveiVision-PRO
cd MuraveiVision-PRO

# Python-окружение (3.12.10)
python -m venv muravei_env          # или использовать существующее
.\muravei_env\Scripts\pip.exe install --no-cache-dir -r backend\requirements.txt

# Фронт
npm install

# Проверка
.\muravei_env\Scripts\python.exe -c "import sys; print(sys.version)"   # -> 3.12...
npm run build
```

## Запуск

| Сценарий | Команда | Описание |
|----------|---------|----------|
| Dev (фронт+бек) | `npm run backend` + `npm run dev` | uvicorn:8000 + vite:3000 |
| API только | `start-backend.bat` | uvicorn 127.0.0.1:8000 |
| Desktop shell | `npm run desktop` | [backend/desktop_launcher.py](../backend/desktop_launcher.py) → pywebview + FastAPI |
| Поле (1 клик) | `Запустить.bat` | (опц.) Ollama → API → health-check → браузер |

## Portable-сборки

Детали упаковки — [PORTABLE.md](PORTABLE.md). Сборщик: [scripts/build_portable.ps1](../scripts/build_portable.ps1) (`$PyVer = "3.12.10"`).

| Тип | Команда | Состав |
|-----|---------|--------|
| Lite | `npm run portable` | embeddable Python 3.12.10 + зависимости + фронт-сборка |
| Full Field Kit | `npm run portable:full` | + Ollama `qwen2.5vl:7b` + CUDA PyTorch + assets моделей |

Важно: portable пекёт **embeddable 3.12.10** в staged `muravei_env`, а не копирует хостовый 3.14.

## Верификация после установки

```powershell
# 1. Бек жив
curl http://127.0.0.1:8000/api/health

# 2. API-приём
.\muravei_env\Scripts\python.exe backend\scripts\smoke_phase3.py

# 3. Фронт-сборка
npm run build

# 4. Backend unit
cd backend; ..\muravei_env\Scripts\python.exe -m unittest discover -s tests
```

## Устранение проблем

| Симптом | Причина / решение |
|---------|-------------------|
| `python` запускает 3.14 | PATH; используйте только `muravei_env\Scripts\python.exe` |
| Порт 8000 занят | другой uvicorn; найдите и остановите, или смените порт |
| CUDA OOM | engine сам откатится на CPU (`device_backend=cpu-fallback-oom`); при частом — снизьте нагрузку |
| Нет весов → `mode=offline` | положите `*.pt` в `runs/detect/train/weights/` или `assets/models/` |
| SAHI `pip check` warning | benign: sahi декларирует `opencv-python>=4.12` (non-headless имя), `cv2` предоставляется headless-сборкой; runtime OK |
| Ollama нет → AI-аналитика недоступна | установите Ollama, остальная система работает |
| `ECONNRESET` в тестах | конкурентные воркеры; в `playwright.config.ts` уже `workers: 1` |

## Обновление

```powershell
git pull
.\muravei_env\Scripts\pip.exe install --no-cache-dir -r backend\requirements.txt
npm install
npm run build
```
Схема БД мигрируется автоматически при старте (`init_db`, аддитивные `ALTER TABLE`).
