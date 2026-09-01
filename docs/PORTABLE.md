# Portable ZIP

## Цель

Полевой комплект Windows: распаковал → `Запустить.bat` → UI на `http://127.0.0.1:8000` **без** установки Node/Python на целевой машине.

Скрипт: [`scripts/build_portable.ps1`](../scripts/build_portable.ps1).

**Python:** только embeddable / `muravei_env` **3.12.10**. Host `C:\Python314` и bare `python` запрещены.

## Сборка Lite (машина разработчика)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1 -FetchEmbeddablePython
# или
npm run portable
```

## Сборка Full Field Kit

Предусловие: на машине сборки уже есть модель:

```powershell
ollama pull qwen2.5vl:7b
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1 -FetchEmbeddablePython -FullKit
# или
npm run portable:full
```

Опционально: `-OllamaZipPath path\to\ollama-windows-amd64.zip`, `-OllamaVersion v0.11.4`, `-OllamaModelsRoot D:\LLM\ollama` (папка с `blobs\` + `manifests\`; по умолчанию ищутся `OLLAMA_MODELS`, `D:\LLM\ollama`, `%USERPROFILE%\.ollama`), `-SkipNpmBuild`, `-SkipZip`.

В FullKit копируется **только** `qwen2.5vl:7b` (~6 GB blobs), не весь локальный store Ollama.

Артефакты:

| Режим | Stage | ZIP |
|-------|-------|-----|
| Lite | `portable/MuraveiVision_PRO_Portable/` | `MuraveiVision_PRO_Portable.zip` |
| Full | `portable/MuraveiVision_PRO_FullKit/` | `MuraveiVision_PRO_FullKit.zip` (Zip64) |

## Что кладётся (Lite)

- `backend/`, `dist/` (с CSP)
- embeddable `muravei_env` + pip из `backend/requirements.txt`
- detect `.pt` (без `*seg*` / `yoloe*` при копировании)
- `military_classes.yaml`, `Запустить.bat`
- опционально `mobileclip2_b.ts`
- пустые `archive/`, `cache/`, `logs/`, `reports/`

**Не копируется** host `muravei_env` с Python 3.14.

## Что добавляет Full Kit

- `ollama/ollama.exe` (+ DLL из `ollama-windows-amd64.zip`)
- `ollama/models/` — копия `%USERPROFILE%\.ollama\models` (должна содержать `qwen2.5vl`)
- `torch`+`torchvision` **cu128** в staged `muravei_env`
- `PORTABLE_README.md`
- `Запустить.bat` поднимает `ollama serve` с `OLLAMA_MODELS=%~dp0ollama\models`

Ожидаемый размер ZIP порядка **12–18 GB**.

## Железо

- Windows 10/11 **amd64** (Intel CPU и AMD — оба OK)
- Рекомендуется **NVIDIA** для realtime
- Без GPU: YOLO/Ollama на CPU (медленно для VLM); Intel Arc/XPU — вне скоупа

## Лаунчер `Запустить.bat`

Файл **ASCII + CRLF** (без кириллицы): так `cmd.exe` не ломает строки (`HOST` / `ON` / обрывки UTF-8).

Если уже распакован старый FullKit ZIP — **достаточно заменить только** `Запустить.bat` из репозитория или из `portable/MuraveiVision_PRO_FullKit/` (пересобирать ~10 GB ZIP не нужно).

## Проверка комплекта

1. Распаковать на чистую машину / другую папку.  
2. `Запустить.bat`.  
3. Логин оператора, архивное видео, YOLO ready.  
4. Full: диспетчер задач → `ollama.exe`; `GET /api/ai/models` → `qwen2.5vl`.  
5. Smoke layout (после stage):  
   `.\muravei_env\Scripts\python.exe backend\scripts\smoke_fullkit_layout.py`
