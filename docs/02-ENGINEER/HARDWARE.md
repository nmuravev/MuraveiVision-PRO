# Hardware — MuraveiVision PRO

> **Аппаратные требования: GPU, CPU, RAM, storage.**

## Обзор

MuraveiVision PRO поддерживает NVIDIA GPU (CUDA), AMD GPU (DirectML) и CPU-only режим. Правильный выбор оборудования критичен для производительности.

## GPU Requirements

### NVIDIA GPU (Recommended)

| Tier | GPU | VRAM | FP16 | CUDA | Performance |
|------|-----|------|------|------|-------------|
| **Tier 1** | RTX 3070/4070 | 8 GB | ✅ | 12.x | Хорошая |
| **Tier 2** | RTX 3080/4080 | 10-12 GB | ✅ | 12.x | Отличная |
| **Tier 3** | RTX 3090/4090 | 24 GB | ✅ | 12.x | Максимальная |

### AMD GPU (DirectML)

| Tier | GPU | VRAM | Performance |
|------|-----|------|-------------|
| **Tier 1** | RX 6600 | 8 GB | Средняя |
| **Tier 2** | RX 6700 XT | 12 GB | Хорошая |
| **Tier 3** | RX 7900 XTX | 24 GB | Отличная |

> **DirectML на ~30-40% медленнее CUDA** при тех же параметрах.

### CPU-only Mode

| Сценарий | Производительность |
|----------|-------------------|
| YOLO-nano | ~50 FPS |
| YOLOv8n | ~10 FPS |
| SAHI (512×512) | ~2 FPS |
| DA3 dense | ❌ Не поддерживается |

## GPU Verification

### Проверка NVIDIA GPU

```bash
# NVIDIA-SMI
nvidia-smi

# Output:
# +-----------------------------------------------------------------------------+
# | NVIDIA-SMI 551.86       Driver Version: 551.86       CUDA Version: 12.4   |
# |-------------------------------+----------------------+----------------------+
# | GPU  Name        TCC/WDDM  | Bus-Id        Disp.A | Volatile Uncorr. ECC |
# | Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
# |   0  NVIDIA RTX 4070  WDDM  |   00000000:01:00.0  On |                  N/A |
# |  45%   52C    P8    12W / 200W |   2048MiB /  8192MiB |     5%      Default |
# +-----------------------------------------------------------------------------+
```

### Проверка CUDA в Python

```python
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA version: {torch.version.cuda}")
print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB")

# Output:
# CUDA available: True
# CUDA version: 12.4
# GPU: NVIDIA GeForce RTX 4070
# VRAM: 8.0 GB
```

## CPU Requirements

### Минимальные требования

| Требование | Значение |
|------------|----------|
| **Архитектура** | x64 |
| **Инструкции** | SSE4.2, AVX2 |
| **Ядра** | 4 |
| **Потоки** | 8 |

### Рекомендуемые

| Требование | Значение |
|------------|----------|
| **Архитектура** | x64 |
| **Инструкции** | SSE4.2, AVX2, FMA |
| **Ядра** | 8+ |
| **Потоки** | 16+ |

### Проверка AVX2

```bash
# Windows
wmic cpu get Name,NumberOfCores,NumberOfLogicalProcessors /format:list

# Linux
lscpu | grep -E "Architecture|CPU op-mode|Model name|Socket|Core|Thread|AVX"
```

## RAM Requirements

### Минимальные

| Компонент | RAM |
|-----------|-----|
| Система | 2 GB |
| Python | 2 GB |
| Browser | 1 GB |
| **Итого минимум** | **8 GB** |

### Рекомендуемые

| Компонент | RAM |
|-----------|-----|
| Система | 4 GB |
| Python | 4 GB |
| Browser | 2 GB |
| CUDA reserve | 2 GB |
| **Итого recommended** | **16 GB** |

### RAM по сценариям

| Сценарий | Минимум | Recommended |
|----------|---------|-------------|
| Detection (single image) | 8 GB | 16 GB |
| Batch scan (100 images) | 16 GB | 32 GB |
| Segmentation + Detection | 16 GB | 32 GB |
| 3D Reconstruction (DA3) | 32 GB | 64 GB |

## Storage Requirements

### Минимальный диск

| Компонент | Размер |
|-----------|--------|
| Приложение | 5 GB |
| Python runtime | 3 GB |
| Models | 4 GB |
| Data (sample) | 10 GB |
| **Итого минимум** | **22 GB** |

### Рекомендуемый диск

| Компонент | Размер |
|-----------|--------|
| Приложение | 10 GB |
| Python runtime | 3 GB |
| Models | 4 GB |
| Data (working) | 100 GB |
| Backups | 50 GB |
| **Итого recommended** | **167 GB** |

### Тип storage

| Тип | Скорость чтения | Скорость записи | Рекомендация |
|-----|-----------------|-----------------|--------------|
| **NVMe SSD** | 3500 MB/s | 3000 MB/s | ✅ Лучший выбор |
| **SATA SSD** | 550 MB/s | 500 MB/s | ✅ Хороший выбор |
| **HDD** | 150 MB/s | 150 MB/s | ⚠️ Только для архива |

## Hardware Compatibility Matrix

### Полная совместимость

| Компонент | Минимум | Recommended | Ideal |
|-----------|---------|-------------|-------|
| **CPU** | x64, 4 cores | 8 cores, AVX2 | 12+ cores, AVX-512 |
| **RAM** | 8 GB | 16 GB | 32 GB+ |
| **GPU VRAM** | 4 GB | 8 GB | 24 GB |
| **GPU** | NVIDIA GTX 1070 | RTX 3070/4070 | RTX 4090 |
| **Storage** | 50 GB HDD | 100 GB SSD | 500 GB NVMe |
| **CUDA** | 11.8 | 12.1 | 12.4 |

## Performance Benchmarks

### Detection FPS (RTX 4070, 8 GB VRAM)

| Модель | 1920×1080 | 3840×2160 | 8192×6144 + SAHI |
|--------|-----------|-----------|-------------------|
| YOLOv8n | 180 FPS | 95 FPS | 12 FPS (64 tiles) |
| YOLOv8s | 95 FPS | 50 FPS | 6 FPS (64 tiles) |
| YOLOv8m | 48 FPS | 25 FPS | 3 FPS (64 tiles) |

### Detection FPS (RTX 3060, 12 GB VRAM)

| Модель | 1920×1080 | 3840×2160 | 8192×6144 + SAHI |
|--------|-----------|-----------|-------------------|
| YOLOv8n | 150 FPS | 80 FPS | 10 FPS (64 tiles) |
| YOLOv8s | 80 FPS | 42 FPS | 5 FPS (64 tiles) |
| YOLOv8m | 40 FPS | 20 FPS | 2.5 FPS (64 tiles) |

### Segmentation FPS (RTX 4070)

| Режим | Разрешение | FPS |
|-------|------------|-----|
| Interactive | 1920×1080 | 30 FPS |
| Interactive | 3840×2160 | 12 FPS |
| Propagate Fast | 1920×1080 | 100 FPS |
| Propagate Balanced | 1920×1080 | 50 FPS |

## Upgrade Recommendations

### Приоритет upgrades

1. **GPU VRAM** — самый важный для производительности
2. **RAM** — критично для batch processing
3. **Storage** — NVMe для скорости I/O
4. **CPU** — менее критичен (инференс на GPU)

### Upgrade paths

```
Current: CPU-only, 8 GB RAM
    ↓ [1] Add GPU (RTX 3070)
Improved: GPU inference, 8 GB RAM
    ↓ [2] Add RAM (16 GB)
Improved: GPU + 16 GB RAM
    ↓ [3] Add NVMe SSD
Optimal: GPU + 16 GB RAM + NVMe
```

## Troubleshooting

### Проблема: GPU не определяется

```
GPU not detected
Solution:
1. Проверьте nvidia-smi
2. Проверьте драйвер (551.86+)
3. Проверьте CUDA (12.x)
4. Проверьте device_id в config
```

### Проблема: CUDA out of memory

```
CUDA out of memory
Solution:
1. Уменьшите batch_size
2. Закройте другие GPU-приложения
3. Используйте YOLOv8n вместо v8s
4. Уменьшите memory_fraction (0.6 вместо 0.8)
```

### Проблема: Медленная работа

```
Slow performance
Solution:
1. Проверьте GPU: nvidia-smi
2. Проверьте режим (CUDA vs CPU)
3. Проверьте VRAM usage
4. Проверьте disk type (SSD vs HDD)
```

## Дальнейшие шаги

1. **[Network Setup](./NETWORK_SETUP.md)** — настройка сети
2. **[Maintenance](./MAINTENANCE.md)** — обслуживание
3. **[Diagnostics](./DIAGNOSTICS.md)** — диагностика
4. **[Updating](./UPDATING.md)** — обновление

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
