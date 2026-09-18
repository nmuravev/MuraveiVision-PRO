# Системные требования — MuraveiVision PRO

> **Критически важно:** MuraveiVision PRO работает в air-gap режиме. Все зависимости должны быть установлены заранее.

## Аппаратные требования

### Процессор

| Уровень | Требования | Поддержка |
|---------|------------|-----------|
| Минимум | x64, 4 ядра | SSE4.2, AVX2 |
| Рекомендуемый | 8+ ядер | AVX2, FMA |
| Идеальный | 12+ ядер | AVX-512 |

> **AVX2 required:** YOLO inference и SAHI-слайсинг используют AVX2-инструкции. Старые CPU не поддерживаются.

### Оперативная память

| Компонент | Минимум | Рекомендуемый |
|-----------|---------|---------------|
| Общая RAM | 8 GB | 16 GB+ |
| Под система | 2 GB | 4 GB |
| Под Python | 2 GB | 4 GB |
| Под браузер | 1 GB | 2 GB |
| Под CUDA | — | 2 GB (резерв) |

### Графический процессор

#### NVIDIA GPU (CUDA)

| Tier | GPU | VRAM | Поддержка |
|------|-----|------|-----------|
| Tier 1 | RTX 3070/4070 | 8 GB | Полная |
| Tier 2 | RTX 3080/4080 | 10-12 GB | Полная + SAHI batch |
| Tier 3 | RTX 3090/4090 | 24 GB | Полная + DA3 dense |

> **CUDA 12.x required:** Поддерживаются CUDA 12.1 — 12.4. Более старые версии НЕ поддерживаются.

#### AMD GPU (DirectML)

| Tier | GPU | VRAM | Поддержка |
|------|-----|------|-----------|
| Tier 1 | RX 6600 | 8 GB | Базовая |
| Tier 2 | RX 6700 XT | 12 GB | Полная |
| Tier 3 | RX 7900 XTX | 24 GB | Полная + DA3 |

> **DirectML:** Медленнее CUDA на ~30-40%. Рекомендуется для тестирования.

#### CPU-only режим

| Сценарий | Производительность |
|----------|-------------------|
| YOLO-nano | ~50 FPS (1 image) |
| YOLOv8n | ~10 FPS |
| SAHI (1024×1024) | ~2 FPS |
| DA3 dense | НЕ ПОДДЕРЖИВАЕТСЯ |

### Хранилище

| Компонент | Минимум | Рекомендуемый |
|-----------|---------|---------------|
| Приложение | 5 GB SSD | 10 GB NVMe |
| Модели | 2 GB | 5 GB |
| Данные | 10 GB | 100 GB+ |
| Swap/Page | 4 GB | 8 GB |

> **NVMe recommended:** При работе с большими видео (4K, 60fps) скорость диска критична.

## Программные требования

### Операционная система

| ОС | Поддержка | Версии |
|----|-----------|--------|
| Windows 10 | ✅ | Pro 21H2+ |
| Windows 11 | ✅ | 22H2+ |
| WSL2 | ⚠️ | Ubuntu 22.04 |
| Linux | ⚠️ | Ubuntu 22.04, Debian 12 |

> **Primary support: Windows 10/11.** Linux/WSL2 поддерживается частично.

### Python

| Компонент | Требование |
|-----------|------------|
| Версия | 3.10 — 3.12 |
| Окружение | venv (обязательно) |
| Pip | Оффлайн-репозиторий |

### Node.js (Frontend)

| Компонент | Требование |
|-----------|------------|
| Версия | 18.x LTS |
| Менеджер | npm (не yarn/pnpm) |
| Зависимости | `npm install` (офлайн) |

### CUDA Toolkit

| Компонент | Требование |
|-----------|------------|
| Версия | 12.1 — 12.4 |
| cuDNN | 9.x для CUDA 12.x |
| TensorRT | Опционально, ускоряет ~2x |

### Ollama (AI-анализ)

| Компонент | Требование |
|-----------|------------|
| Версия | 0.2.x+ |
| Модель | llama3.2, mistral-nemo |
| VRAM | 4 GB минимум |

## Проверка совместимости

### Автоматическая диагностика

```bash
# Запуск диагностики оборудования
muravei_env\Scripts\python.exe backend/scripts/diagnose.py

# Вывод:
# [OK] Python 3.11.9
# [OK] CUDA 12.4, driver 551.86
# [OK] GPU: NVIDIA GeForce RTX 4070 (8 GB VRAM)
# [OK] AVX2: supported
# [OK] RAM: 16 GB
# [OK] Disk: NVMe SSD (500 MB/s)
# [WARN] Ollama: not installed
# [OK] Docker: not required
```

### Ручная проверка CUDA

```python
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA version: {torch.version.cuda}")
print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB")
```

### Ручная проверка AVX2

```bash
# Windows
wmic cpu get Name,NumberOfCores,NumberOfLogicalProcessors /format:list

# Linux
lscpu | grep -E "Architecture|CPU op-mode|Model name|Socket|Core|Thread|AVX"
```

## Треки VRAM и производительности

### VRAM budget (YOLO + SAHI)

```
Base model load:        250 MB
YOLOv8n weights:        6 MB
YOLOv8s weights:       22 MB
YOLOv8m weights:       50 MB
SAHI context (per tile): 100 MB × tiles
Batch buffer:           200 MB × batch_size
Segmentation masks:     50 MB × images
```

**Пример:** YOLOv8s + SAHI (4×4 grid) + batch 4:
```
22 + (100 × 16) + (200 × 4) = 22 + 1600 + 800 = 2422 MB
```

### VRAM budget (DA3 Dense)

```
Depth model (DA3-S):    2.1 GB
Depth model (DA3-B):    4.3 GB
Point cloud buffer:     500 MB × images
Mesh buffer:            1 GB × scene
```

## Air-gap требования

### Предварительная подготовка

Все пакеты должны быть загружены заранее:

```bash
# На машине с интернетом
pip download -r requirements.txt -d ./offline-packages
pip download -r requirements-dev.txt -d ./offline-packages

# npm пакеты (если нужно)
cd MurVis && npm pack --offline
cd ..
```

### Установка в air-gap

```bash
# Python
pip install --no-index --find-links=./offline-packages -r requirements.txt

# Проверка
pip check
```

## Минимальный портативный набор

Для полностью автономной работы:

| Компонент | Размер |
|-----------|--------|
| Приложение | 500 MB |
| Python runtime | 300 MB |
| YOLOv8n model | 6 MB |
| SAM3 model | 1.5 GB |
| DA3-S model | 2.1 GB |
| Ollama models | 4 GB |
| **Итого** | **~8.4 GB** |

> **Рекомендация:** Используйте SSD минимум на 50 GB для резерва данных.
