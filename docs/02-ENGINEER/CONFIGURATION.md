# Configuration — MuraveiVision PRO

> **Полная конфигурация: SQLite, SAHI, JWT, GPU, logging.**

## Обзор конфигурации

MuraveiVision PRO использует YAML-конфигурацию в `config/custom.yaml`. Все параметры разделены на секции.

## Основная конфигурация

```yaml
# config/custom.yaml

# === General ===
app:
  name: "MuraveiVision PRO"
  version: "3.2.0"
  debug: false
  log_level: "INFO"

# === Database ===
database:
  url: "sqlite:///data/muravei.db"
  wal_mode: true
  timeout: 30
  busy_timeout: 5000
  backup_interval_hours: 24
  max_connections: 10

# === GPU ===
gpu:
  device: "cuda"          # cuda | directml | cpu
  device_id: 0
  batch_size: 4
  fp16: true
  memory_fraction: 0.8

# === SAHI ===
sahi:
  enabled: true
  slice_height: 512
  slice_width: 512
  overlap_percentage: 20
  min_object_size: 100

# === Detection ===
detection:
  model: "yolo26s-ft"
  threshold: 0.50
  iou: 0.45
  max_detections: 100
  class_filter: []        # empty = all classes

# === Security ===
security:
  jwt_secret: "your-secret-here"
  jwt_algorithm: "HS256"
  jwt_expire_minutes: 1440
  rate_limit: "100/min"
  cors_origins:
    - "http://localhost:5173"
    - "http://localhost:8000"

# === Logging ===
logging:
  level: "INFO"
  file: "data/logs/app.log"
  max_size_mb: 100
  backup_count: 5
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# === Network ===
network:
  mode: "standalone"      # standalone | hub | client
  host: "0.0.0.0"
  port: 8000
  ws_port: 8765

# === Backup ===
backup:
  enabled: true
  interval_hours: 24
  retention_days: 30
  destination: "data/backups/"
  compress: true
```

## SQLite Configuration

### Параметры БД

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| **url** | string | `sqlite:///data/muravei.db` | Путь к БД |
| **wal_mode** | bool | `true` | Write-Ahead Logging |
| **timeout** | int | `30` | Timeout в секундах |
| **busy_timeout** | int | `5000` | Busy timeout в мс |
| **max_connections** | int | `10` | Макс подключений |

### WAL Mode

```yaml
# WAL (Write-Ahead Logging)
database:
  wal_mode: true

# Преимущества:
# • Чтение не блокирует запись
# • Запись не блокирует чтение
# • Лучшая производительность при конкурентном доступе
# • Автоматическая checkpoint
```

### Backup

```yaml
database:
  backup_interval_hours: 24
  destination: "data/backups/"
  compress: true
  retention_days: 30

# Пример:
# data/backups/muravei_20260919_120000.db.gz
```

## SAHI Configuration

### Параметры SAHI

| Параметр | Диапазон | По умолчанию | Описание |
|----------|----------|--------------|----------|
| **slice_height** | 256-2048 | 512 | Высота слайса |
| **slice_width** | 256-2048 | 512 | Ширина слайса |
| **overlap_percentage** | 0-50 | 20 | Перекрытие |
| **min_object_size** | 10-1000 | 100 | Мин размер объекта (px²) |

### Рекомендации

```yaml
# Для мелких объектов (муравьи)
sahi:
  slice_height: 512
  slice_width: 512
  overlap_percentage: 30
  min_object_size: 50

# Для крупных объектов
sahi:
  slice_height: 1024
  slice_width: 1024
  overlap_percentage: 10
  min_object_size: 500

# Для скорости
sahi:
  slice_height: 1024
  slice_width: 1024
  overlap_percentage: 10
  min_object_size: 200
```

## JWT Configuration

### Генерация secret

```bash
# Генерация случайного secret
muravei_env\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
# 'a1b2c3d4e5f6...'
```

### Параметры JWT

```yaml
security:
  jwt_secret: "a1b2c3d4e5f6..."  # ← сгенерируйте свой!
  jwt_algorithm: "HS256"          # HS256 | RS256
  jwt_expire_minutes: 1440        # 24 часа
  rate_limit: "100/min"           # 100 запросов/мин
```

### Алгоритмы

| Алгоритм | Безопасность | Скорость | Использование |
|----------|--------------|----------|---------------|
| **HS256** | Средняя | Быстрая | Single-machine |
| **RS256** | Высокая | Средняя | Network setup |

## GPU Configuration

### Параметры GPU

```yaml
gpu:
  device: "cuda"          # cuda | directml | cpu
  device_id: 0            # Индекс GPU
  batch_size: 4           # Batch size для inference
  fp16: true              # FP16 precision
  memory_fraction: 0.8    # Доля VRAM (0.0-1.0)
```

### Device selection

```yaml
# NVIDIA GPU (recommended)
gpu:
  device: "cuda"
  device_id: 0
  fp16: true

# AMD GPU (DirectML)
gpu:
  device: "directml"
  device_id: 0
  fp16: false

# CPU-only (fallback)
gpu:
  device: "cpu"
  batch_size: 1
  fp16: false
```

### Batch size optimization

| VRAM | Batch size | Speed | Memory |
|------|------------|-------|--------|
| 4 GB | 1 | 1x | ~1.5 GB |
| 8 GB | 4 | 3x | ~3.0 GB |
| 12 GB | 8 | 5x | ~5.0 GB |
| 24 GB | 16 | 7x | ~9.0 GB |

## Logging Configuration

### Параметры logging

```yaml
logging:
  level: "INFO"           # DEBUG | INFO | WARNING | ERROR
  file: "data/logs/app.log"
  max_size_mb: 100
  backup_count: 5
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

### Rotation

```
Log rotation:
app.log              ← current
app.log.1            ← 100 MB
app.log.2            ← 100 MB
...
app.log.5            ← 100 MB
Total: ~500 MB
```

### Log levels

| Level | Использование |
|-------|---------------|
| **DEBUG** | Отладка, подробный вывод |
| **INFO** | Обычная работа (по умолчанию) |
| **WARNING** | Предупреждения, но работает |
| **ERROR** | Ошибки, некоторые функции не работают |

## Network Configuration

### Modes

```yaml
# Standalone (single machine)
network:
  mode: "standalone"
  host: "0.0.0.0"
  port: 8000

# Hub (central server)
network:
  mode: "hub"
  host: "0.0.0.0"
  port: 8000
  ws_port: 8765

# Client (connected to hub)
network:
  mode: "client"
  hub_url: "http://hub-server:8000"
  host: "0.0.0.0"
  port: 8000
```

### WebSocket channels

```yaml
network:
  ws_port: 8765
  channels:
    n1: "status"       # Status updates
    n2: "detections"   # Detection results
    n3: "segments"     # Segmentation data
    n4: "chat"         # Chat messages
    n5: "files"        # File transfer
    n6: "location"     # Location sharing
```

## Дальнейшие шаги

1. **[Models](./MODELS.md)** — управление моделями
2. **[Hardware](./HARDWARE.md)** — оборудование
3. **[Network Setup](./NETWORK_SETUP.md)** — сеть
4. **[Maintenance](./MAINTENANCE.md)** — обслуживание

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
