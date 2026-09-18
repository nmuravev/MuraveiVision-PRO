# Diagnostics — MuraveiVision PRO

> **Диагностика: session trace, smoke tests, GPU, network, database.**

## Обзор

Диагностика — ключевая часть обслуживания MuraveiVision PRO. Включает: session trace, smoke tests, GPU diagnostics, network diagnostics, database diagnostics.

## Session Trace

### Включение

```yaml
# config/custom.yaml
logging:
  session_trace:
    enabled: true
    level: "detailed"    # basic | detailed | verbose
    file: "data/logs/session_trace.log"
    max_size_mb: 50
```

### Просмотр

```
Session Trace:
┌─────────────────────────────────────────┐
│  Session: field_session_01              │
│  Started: 10:00:00                      │
│  Duration: 2h 30m                       │
│                                         │
│  Timeline:                              │
│  10:00:00  Session start               │
│  10:00:05  Media loaded: IMG_001.jpg   │
│  10:00:10  Detection started            │
│  10:00:12  Detection complete: 12 objs │
│  10:05:00  Segmentation started         │
│  10:05:03  Segmentation complete: 3 msks│
│  ...                                     │
│  12:30:00  Session end                 │
│                                         │
│  [📄 Export] [🔍 Filter] [📊 Stats]    │
└─────────────────────────────────────────┘
```

## Smoke Tests

### Запуск

```bash
# All smoke tests
muravei_env\Scripts\python.exe -m pytest backend/tests/smoke/ -q

# Output:
# 12 passed in 3.45s

# Specific test
muravei_env\Scripts\python.exe -m pytest backend/tests/smoke/test_health.py -v
```

### Smoke test suite

| Test | Описание | Время |
|------|----------|-------|
| **test_health** | Health endpoint | 0.1s |
| **test_db** | Database connectivity | 0.2s |
| **test_gpu** | GPU availability | 0.5s |
| **test_model_load** | Model loading | 2.0s |
| **test_detection** | Single detection | 1.0s |
| **test_frontend** | Frontend accessible | 0.3s |

## GPU Diagnostics

### Проверка GPU

```bash
# NVIDIA-SMI
nvidia-smi

# PyTorch CUDA check
muravei_env\Scripts\python.exe -c "
import torch
print(f'CUDA: {torch.cuda.is_available()}')
print(f'Version: {torch.version.cuda}')
print(f'GPU: {torch.cuda.get_device_name(0)}')
print(f'VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB')
"
```

### GPU diagnostics script

```bash
muravei_env\Scripts\python.exe backend/scripts/gpu_diagnostics.py

# Output:
# ========================================
# GPU Diagnostics
# ========================================
# [OK] CUDA available: True
# [OK] CUDA version: 12.4
# [OK] Driver: 551.86
# [OK] GPU: NVIDIA GeForce RTX 4070
# [OK] VRAM: 8.0 GB
# [OK] Free VRAM: 5.9 GB
# [OK] GPU temperature: 52°C
# [OK] GPU utilization: 5%
# [OK] AVX2: supported
# ========================================
```

### GPU monitoring

```bash
# Continuous monitoring
muravei_env\Scripts\python.exe backend/scripts/gpu_monitor.py --interval 5

# Output:
# [10:00:00] VRAM: 2.1/8.0 GB (26%) | Temp: 52°C | Util: 5%
# [10:00:05] VRAM: 2.3/8.0 GB (29%) | Temp: 53°C | Util: 8%
# [10:00:10] VRAM: 2.2/8.0 GB (28%) | Temp: 52°C | Util: 6%
```

## Network Diagnostics

### Проверка сети

```bash
# Ping hub
ping 192.168.1.100

# Telnet port
telnet 192.168.1.100 8000

# WebSocket test
muravei_env\Scripts\python.exe backend/scripts/ws_test.py \
  --url ws://192.168.1.100:8765
```

### Network diagnostics script

```bash
muravei_env\Scripts\python.exe backend/scripts/network_diagnostics.py

# Output:
# ========================================
# Network Diagnostics
# ========================================
# [OK] Hub: reachable (192.168.1.100)
# [OK] Port 8000: open
# [OK] Port 8765: open
# [OK] WebSocket: connected
# [OK] Latency: 2 ms
# [OK] Bandwidth: 945 Mbps
# [OK] DNS: resolved
# ========================================
```

## Database Diagnostics

### Integrity check

```bash
muravei_env\Scripts\python.exe backend/scripts/db_check.py

# Output:
# ========================================
# Database Diagnostics
# ========================================
# [OK] Integrity: OK
# [OK] Tables: 8
# [OK] Total size: 45 MB
# [OK] Indexes: 12 (all valid)
# [OK] WAL mode: enabled
# [OK] Connections: 2/10
# ========================================
```

### Size analysis

```bash
muravei_env\Scripts\python.exe backend/scripts/db_size.py

# Output:
# muravei.db: 45 MB
# ├── sessions: 12 MB (27%)
# ├── detections: 20 MB (44%)
# ├── segments: 8 MB (18%)
# ├── models: 2 MB (4%)
# └── other: 3 MB (7%)
```

## Performance Profiling

### CPU profiling

```bash
muravei_env\Scripts\python.exe backend/scripts/profile.py --cpu

# Output:
# ========================================
# CPU Profile
# ========================================
# Total time: 45.23s
# CPU usage: 65%
# Top functions:
#   1. detect() - 18.5s (41%)
#   2. sahi_slice() - 12.3s (27%)
#   3. nms() - 8.2s (18%)
#   4. load_model() - 3.1s (7%)
#   5. other - 3.1s (7%)
# ========================================
```

### Memory profiling

```bash
muravei_env\Scripts\python.exe backend/scripts/profile.py --memory

# Output:
# ========================================
# Memory Profile
# ========================================
# Total RAM: 16 GB
# Used: 11.2 GB (70%)
# Free: 4.8 GB (30%)
# Python: 2.1 GB
# Browser: 1.8 GB
# System: 3.2 GB
# Other: 4.1 GB
# ========================================
```

## Error Codes

### Table of error codes

| Code | Описание | Решение |
|------|----------|---------|
| **E001** | Backend not running | Запустите backend |
| **E002** | Database error | Проверьте БД: db_check.py |
| **E003** | GPU not available | Проверьте CUDA/nvidia-smi |
| **E004** | Model not found | Загрузите модель |
| **E005** | Disk space low | Cleanup: cleanup.py |
| **E006** | Network timeout | Проверьте сеть |
| **E007** | WebSocket disconnected | Переподключитесь |
| **E008** | JWT expired | Обновите token |
| **E009** | File not found | Проверьте путь |
| **E010** | Invalid format | Конвертируйте файл |

## Diagnostic Commands Reference

### Быстрая диагностика

```bash
# Full diagnostics
muravei_env\Scripts\python.exe backend/scripts/diagnose.py

# Quick health
curl http://localhost:8000/health

# GPU check
nvidia-smi

# DB check
muravei_env\Scripts\python.exe backend/scripts/db_check.py

# Network check
muravei_env\Scripts\python.exe backend/scripts/network_diagnostics.py
```

### Log analysis

```bash
# View recent errors
findstr /C:"ERROR" data\logs\app.log | more

# View session trace
type data\logs\session_trace.log | more

# View WebSocket events
type data\logs\websocket.log | more
```

## Troubleshooting

### Проблема: Диагностика не проходит

```
Diagnostics failed
Solution:
1. Проверьте logs: data/logs/
2. Запустите diagnose.py
3. Проверьте каждый компонент отдельно
4. Проверьте права доступа
```

## Дальнейшие шаги

1. **[Updating](./UPDATING.md)** — обновление
2. **[Maintenance](./MAINTENANCE.md)** — обслуживание
3. **[Models](./MODELS.md)** — управление моделями

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
