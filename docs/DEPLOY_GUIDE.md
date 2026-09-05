# Offline env pack (wheels)

Отдельный дистрибутив Python-зависимостей **без** копирования `muravei_env` (venv хранит абсолютные пути и ломается на чужой машине).

См. также: [DEPLOYMENT.md](DEPLOYMENT.md), [ENGINEER_GUIDE.md](ENGINEER_GUIDE.md), [PORTABLE.md](PORTABLE.md), [SPEC_FIELD_MACBOOK.md](SPEC_FIELD_MACBOOK.md).

## Поле (коллега)

1. Клонировать/скопировать репозиторий (или исходники без `muravei_env`).
2. Распаковать пак **в корень проекта** (появятся `wheels/`, `README_PACK.txt`, …):
   - NVIDIA → `muravei_env_pack_win_cuda.zip`
   - Intel + AMD (без NVIDIA) → `muravei_env_pack_win_cpu.zip`
3. Запустить `scripts\setup_env.bat`  
   — или просто `Запустить.bat` (сам вызовет setup, если env нет).
4. Дождаться `Готово: muravei_env установлен.`
5. Дальше обычный запуск API/UI.

Интернет на полевой машине **не нужен**, если `wheels/` полный.

## Dev (сборка пака)

На машине с рабочим `muravei_env` (3.12.10) и сетью:

```powershell
# NVIDIA / CUDA torch (~3 GB):
.\scripts\make_env_pack.ps1 -TorchFlavor cuda
# → dist\muravei_env_pack_win_cuda.zip

# Intel+AMD / CPU torch + DirectML ORT (~1 GB):
.\scripts\make_env_pack.ps1 -TorchFlavor cpu
# → dist\muravei_env_pack_win_cpu.zip
```

Результат: ZIP + размер/sha256 в консоли (сборка через `tar`/Zip64).  
ZIP **не коммитится** — артефакт релиза/флешки.

Шаблон манифеста: [`scripts/wheels_manifest.example.json`](../scripts/wheels_manifest.example.json).  
Внутри ZIP: `scripts/wheels_manifest.json` (имена + sha256 каждого wheel).

## Intel + AMD (без NVIDIA)

Целевая машина: MacBook Pro (Intel) + Boot Camp + Radeon Pro 5500M — [SPEC_FIELD_MACBOOK.md](SPEC_FIELD_MACBOOK.md).

| Что | Как |
|-----|-----|
| YOLO | DirectML (DX12), experimental; badge `YOLO: DirectML` / fallback `YOLO: CPU` |
| COLMAP | только CPU; max_image_size≈1200, frames≈150–300; ETA часы на 9‑мин клипе |
| Dense/Mesh | off по умолчанию (`MURAVEI_CPU_DISABLE_DENSE=1`); hint «CPU: 1–3 часа» |
| gsplat | disabled: «требуется NVIDIA CUDA» |
| Пак | только `muravei_env_pack_win_cpu.zip` |

**WSL2 (track B, опционально):** проект в `~/MuraveiVision-PRO`, **не** `/mnt/c/...`. На AMD в WSL2 CUDA всё равно нет — GPU-детекция остаётся на native Windows + DirectML.

Ожидаемые времена (ориентир, 9‑мин клип / сегмент ~60с / ~200 кадров): COLMAP sparse — десятки минут–2ч; Dense на CPU — 1–3ч (если включают); YOLO DirectML — быстрее чистого CPU, медленнее NVIDIA CUDA.

## Что делает setup_env

| Условие | Действие |
|---------|----------|
| Есть `muravei_env\Scripts\python.exe` | Пропуск, exit 0 |
| Есть `wheels/` | `pip install --no-index --find-links=wheels/ -r backend/requirements.txt` |
| Нет wheels, есть интернет | Установка с PyPI |
| Нет wheels и нет сети | RU-ошибка: распакуйте `muravei_env_pack_win_*.zip` |
| Нет Python 3.12 | RU-ошибка с просьбой установить 3.12.x |

Проверка: `import torch, fastapi, ultralytics`. CUDA/gsplat — только предупреждения.

## Troubleshooting

| Симптом | Что сделать |
|---------|-------------|
| «Не найден Python 3.12» | Установить Python **3.12.10** (не 3.14). `py -3.12` должен работать. |
| «нет wheels/ и нет интернета» | Распаковать пак в корень (рядом с `backend/`). |
| Offline pip падает | Пак собран под другую платформу/версию Python — пересобрать `make_env_pack.ps1` на 3.12. |
| Torch/CUDA warning на AMD | Нужен **win_cpu** пак, не win_cuda. |
| DirectML не включается | Установлен `onnxruntime-gpu` вместо `onnxruntime-directml`; переустановите CPU-пак. |
| `Запустить.bat` не стартует backend | Сначала добейте `setup_env.bat` до exit 0 — иначе half-broken env не запускается. |

## Связь с portable ZIP

`build_portable.ps1 -FullKit -TorchFlavor cpu|cuda` — отдельный канал (embeddable Python).  
Env-пак — способ поднять **dev/исходники** на полевой машине офлайн без копирования venv.
