# Инженер — MuraveiVision PRO

> **Руководство для инженера:** развёртывание, конфигурация, обслуживание, диагностика.

## Введение

Это руководство предназначено для инженеров — специалистов, которые разворачивают, настраивают и обслуживают MuraveiVision PRO на рабочих машинах.

## Основные возможности

| Возможность | Описание | Документация |
|-------------|----------|--------------|
| **Deployment** | Установка и развёртывание | [Deployment](./DEPLOYMENT.md) |
| **Configuration** | SQLite, SAHI, validator, JWT | [Configuration](./CONFIGURATION.md) |
| **Models** |_weights, import, class catalog_ | [Models](./MODELS.md) |
| **Hardware** | GPU detection, VRAM tiers, CUDA | [Hardware](./HARDWARE.md) |
| **Network Setup** | hub+client, JWT, WebSocket | [Network Setup](./NETWORK_SETUP.md) |
| **Maintenance** | Backups, updates, logging | [Maintenance](./MAINTENANCE.md) |
| **Diagnostics** | Session trace, YOLO debug, smoke | [Diagnostics](./DIAGNOSTICS.md) |
| **Updating** | Version upgrades, migrations | [Updating](./UPDATING.md) |

## Рабочий процесс инженера

```
Подготовка машины
    ↓
Установка Python + Node.js
    ↓
Клонирование репозитория
    ↓
Установка зависимостей
    ↓
Загрузка моделей
    ↓
Конфигурация (YAML)
    ↓
Диагностика
    ↓
Запуск и мониторинг
    ↓
Резервное копирование
```

## Ключевые конфигурационные файлы

| Файл | Назначение | Путь |
|------|------------|------|
| **custom.yaml** | Основная конфигурация | `config/custom.yaml` |
| **class_colors.yaml** | Цвета классов | `config/class_colors.yaml` |
| **models.yaml** | Список моделей | `config/models.yaml` |
| **network.yaml** | Сетевые настройки | `config/network.yaml` |
| **backup.yaml** | Резервное копирование | `config/backup.yaml` |

## Команды инженера

### Базовые команды

```bash
# Диагностика системы
muravei_env\Scripts\python.exe backend/scripts/diagnose.py

# Инициализация БД
muravei_env\Scripts\python.exe backend/scripts/init_db.py

# Резервное копирование
muravei_env\Scripts\python.exe backend/scripts/backup.py --full

# Очистка кэша
muravei_env\Scripts\python.exe backend/scripts/cleanup.py --all

# Обновление моделей
muravei_env\Scripts\python.exe backend/scripts/update_models.py
```

### Мониторинг

```bash
# Проверка здоровья backend
curl http://localhost:8000/health

# Проверка GPU
nvidia-smi

# Мониторинг БД
muravei_env\Scripts\python.exe backend/scripts/db_monitor.py

# Логи
type data\logs\app.log
```

## Troubleshooting

### Проблема: Backend не запускается

```
Error: Port 8000 already in use
Solution:
1. Найдите процесс: netstat -ano | findstr :8000
2. Убейте процесс: taskkill /PID <PID> /F
3. Или измените порт в config/custom.yaml
```

### Проблема: GPU не используется

```
Error: CUDA not available
Solution:
1. Проверьте nvidia-smi
2. Проверьте CUDA toolkit: nvcc --version
3. переустановите PyTorch с CUDA
4. Проверьте драйвер NVIDIA
```

### Проблема: Мало disk space

```
Low disk space
Solution:
1. Очистите кэш: cleanup.py --all
2. Удалите старые backups
3. Архивируйте старые сессии
4. Перенесите data на другой диск
```

## Дальнейшие шаги

1. **[Deployment](./DEPLOYMENT.md)** — подробное развёртывание
2. **[Configuration](./CONFIGURATION.md)** — настройка параметров
3. **[Hardware](./HARDWARE.md)** — GPU и оборудование
4. **[Diagnostics](./DIAGNOSTICS.md)** — диагностика

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
