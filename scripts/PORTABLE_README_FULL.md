# MuraveiVision PRO — Full Field Kit v3.2

## Быстрый старт

1. Распакуйте ZIP на SSD (рекомендуется ≥20 GB свободно).
2. Запустите `Запустить.bat` (логи → `logs\`).
3. Откроется браузер: http://127.0.0.1:8000
4. PIN оператора: `1234567` (инженер `0000000`, мастер `0987907`)

## Состав комплекта

- MuraveiVision PRO (React UI + FastAPI)
- Embeddable **Python 3.12.10** в `muravei_env\` (+ CUDA torch cu128)
- YOLO detect weights (`yolo26n-ft.pt` при наличии; **без SAM/seg**)
- **Ollama** Windows amd64 в `ollama\` (runtime). **VL-модель не в ZIP** — на цели: `ollama pull qwen2.5vl:7b`
- **3D sidecars:** `sidecars\colmap`, `sidecars\gsplat_examples`, AliceVision (если в сборке)
- Опционально `assets\models\mobileclip2_b.ts` (find-similar)

## Распространение

Бинарные паки **не** публикуются на GitHub. Внутренний офлайн-канал; сборка: `scripts\build_portable.ps1`.

## Требования

- Windows 10/11 **64-bit** (процессор **Intel или AMD** amd64)
- **Рекомендуется NVIDIA GPU** (RTX 3060+ / ≥8 GB VRAM) для realtime YOLO и VLM
- Без NVIDIA система **запускается** (CPU fallback), но `qwen2.5vl:7b` будет очень медленным — желательно ≥32 GB RAM
- Intel Arc / OpenVINO отдельно не поддерживаются в этом комплекте

## Режимы

| Комплект | Ollama / 3D | Назначение |
|----------|-------------|------------|
| **Mini** (`-NoDetectWeights`) | нет | UI/geo/отчёты без YOLO-весов |
| **Lite** | нет | Детекция YOLO, отчёты, гео; VLM — если Ollama уже в системе |
| **Full** | да + COLMAP/gsplat sidecars | Детекция + VLM + 3D recon без интернета |

## Сеть (опционально)

Вкладка **Система** → **Сеть** — server/client для обмена целями между базами.

## Остановка

- Закройте окно **MuraveiVision Backend**.
- При необходимости завершите процесс `ollama.exe` в диспетчере задач.

## Сборка (машина разработчика)

Только `muravei_env\Scripts\python.exe` (3.12.10), не system Python 3.14.

```powershell
ollama pull qwen2.5vl:7b
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1 -FetchEmbeddablePython -FullKit
# или: npm run portable:full
```
