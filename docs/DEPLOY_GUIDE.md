# Offline env pack (wheels)

Отдельный дистрибутив Python-зависимостей **без** копирования `muravei_env` (venv хранит абсолютные пути и ломается на чужой машине).

См. также: [DEPLOYMENT.md](DEPLOYMENT.md), [ENGINEER_GUIDE.md](ENGINEER_GUIDE.md), [PORTABLE.md](PORTABLE.md).

## Поле (коллега)

1. Клонировать/скопировать репозиторий (или исходники без `muravei_env`).
2. Распаковать `muravei_env_pack.zip` **в корень проекта** (появятся `wheels/`, `README_PACK.txt`, …).
3. Запустить `scripts\setup_env.bat`  
   — или просто `Запустить.bat` (сам вызовет setup, если env нет).
4. Дождаться `Готово: muravei_env установлен.`
5. Дальше обычный запуск API/UI.

Интернет на полевой машине **не нужен**, если `wheels/` полный.

## Dev (сборка пака)

На машине с рабочим `muravei_env` (3.12.10) и сетью:

```powershell
.\scripts\make_env_pack.ps1
# опционально без CUDA-torch:
.\scripts\make_env_pack.ps1 -WithTorchCu128:$false
```

Результат: `dist/muravei_env_pack.zip` + размер/sha256 в консоли  
(с CUDA torch cu128 типично ~2.9 GB; сборка через `tar`/Zip64, не `Compress-Archive`).  
ZIP **не коммитится** — артефакт релиза/флешки.

Шаблон манифеста: [`scripts/wheels_manifest.example.json`](../scripts/wheels_manifest.example.json).  
Внутри ZIP: `scripts/wheels_manifest.json` (имена + sha256 каждого wheel).

## Что делает setup_env

| Условие | Действие |
|---------|----------|
| Есть `muravei_env\Scripts\python.exe` | Пропуск, exit 0 |
| Есть `wheels/` | `pip install --no-index --find-links=wheels/ -r backend/requirements.txt` |
| Нет wheels, есть интернет | Установка с PyPI |
| Нет wheels и нет сети | RU-ошибка: распакуйте `muravei_env_pack.zip` |
| Нет Python 3.12 | RU-ошибка с просьбой установить 3.12.x |

Проверка: `import torch, fastapi, ultralytics`. CUDA/gsplat — только предупреждения.

## Troubleshooting

| Симптом | Что сделать |
|---------|-------------|
| «Не найден Python 3.12» | Установить Python **3.12.10** (не 3.14). `py -3.12` должен работать. |
| «нет wheels/ и нет интернета» | Распаковать пак в корень (рядом с `backend/`). |
| Offline pip падает | Пак собран под другую платформу/версию Python — пересобрать `make_env_pack.ps1` на 3.12. |
| Torch/CUDA warning | Для GPU пересоберите пак с `-WithTorchCu128` (по умолчанию включено) или поставьте cu128 вручную при наличии сети. |
| `Запустить.bat` не стартует backend | Сначала добейте `setup_env.bat` до exit 0 — иначе half-broken env не запускается. |

## Связь с portable ZIP

Основной portable (`build_portable.ps1`) **не трогаем** — это другой канал (embeddable Python + полный кит).  
Env-пак — лёгкий способ поднять **dev/исходники** на полевой машине офлайн.
