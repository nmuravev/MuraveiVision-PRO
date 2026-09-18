# Maintenance — MuraveiVision PRO

> **Обслуживание: backup, logs, database, health monitoring.**

## Обзор

Регулярное обслуживание критично для стабильной работы MuraveiVision PRO. Основные задачи: резервное копирование, управление логами, обслуживание БД, мониторинг здоровья.

## Backup Strategies

### Типы backup

| Тип | Содержимое | Размер | Частота |
|-----|------------|--------|---------|
| **Full** | Всё (БД + data + config) | 2-5 GB | Ежедневно |
| **Database** | Только БД | 10-100 MB | Ежедневно |
| **Incremental** | Изменения за период | 100-500 MB | Ежечасно |

### Backup schedule

```yaml
# config/backup.yaml
backup:
  full:
    enabled: true
    schedule: "0 2 * * *"      # Daily at 2 AM
    retention_days: 30
    destination: "data/backups/full/"

  database:
    enabled: true
    schedule: "0 */6 * * *"    # Every 6 hours
    retention_days: 90
    destination: "data/backups/db/"

  incremental:
    enabled: true
    schedule: "0 * * * *"      # Hourly
    retention_days: 7
    destination: "data/backups/incr/"
```

### Ручной backup

```bash
# Full backup
muravei_env\Scripts\python.exe backend/scripts/backup.py --full

# Database only
muravei_env\Scripts\python.exe backend/scripts/backup.py --db

# Specific date range
muravei_env\Scripts\python.exe backend/scripts/backup.py \
  --from 2026-09-01 --to 2026-09-19

# Output:
# [OK] Backup created: data/backups/full/muravei_20260919_020000.db.gz
# [OK] Size: 1.2 MB (compressed)
# [OK] Checksum: sha256:a1b2c3d4...
```

### Restore

```bash
# Restore from backup
muravei_env\Scripts\python.exe backend/scripts/backup.py \
  --restore --file data/backups/full/muravei_20260919_020000.db.gz

# Verify before restore
muravei_env\Scripts\python.exe backend/scripts/backup.py \
  --verify --file data/backups/full/muravei_20260919_020000.db.gz
```

## Log Management

### Log rotation

```yaml
# config/custom.yaml
logging:
  level: "INFO"
  file: "data/logs/app.log"
  max_size_mb: 100
  backup_count: 5
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Rotation:
# app.log          ← current (up to 100 MB)
# app.log.1        ← 100 MB
# app.log.2        ← 100 MB
# app.log.3        ← 100 MB
# app.log.4        ← 100 MB
# app.log.5        ← 100 MB
# Total: ~500 MB
```

### Log files

| Файл | Назначение | Путь |
|------|------------|------|
| **App log** | Основные логи | `data/logs/app.log` |
| **WebSocket log** | WS события | `data/logs/websocket.log` |
| **Error log** | Ошибки | `data/logs/error.log` |
| **Access log** | HTTP запросы | `data/logs/access.log` |
| **Backup log** | Backup события | `data/logs/backup.log` |

### Cleanup logs

```bash
# Cleanup old logs
muravei_env\Scripts\python.exe backend/scripts/cleanup.py --logs --days 30

# Cleanup all
muravei_env\Scripts\python.exe backend/scripts/cleanup.py --all

# Output:
# [OK] Removed 15 old log files
# [OK] Freed 245 MB
```

## Database Maintenance

### Vacuum and optimize

```bash
# VACUUM (reclaim space)
muravei_env\Scripts\python.exe backend/scripts/db_vacuum.py

# Optimize indexes
muravei_env\Scripts\python.exe backend/scripts/db_optimize.py

# Check integrity
muravei_env\Scripts\python.exe backend/scripts/db_check.py

# Output:
# [OK] Database integrity: OK
# [OK] Tables: 8
# [OK] Total size: 45 MB
# [OK] Indexes: 12 (all valid)
```

### Database size monitoring

```bash
# Check DB size
muravei_env\Scripts\python.exe backend/scripts/db_size.py

# Output:
# muravei.db: 45 MB
# ├── sessions: 12 MB
# ├── detections: 20 MB
# ├── segments: 8 MB
# ├── models: 2 MB
# └── other: 3 MB
```

### Auto-vacuum

```yaml
database:
  auto_vacuum:
    enabled: true
    interval_days: 7
    time: "03:00"
```

## Health Monitoring

### Automated checks

```yaml
# config/health.yaml
health:
  checks:
    - name: "backend_running"
      interval_seconds: 60
      command: "curl http://localhost:8000/health"

    - name: "database_writable"
      interval_seconds: 300
      command: "python backend/scripts/db_check.py"

    - name: "disk_space"
      interval_seconds: 3600
      min_free_gb: 10

    - name: "gpu_available"
      interval_seconds: 120
      command: "nvidia-smi"

    - name: "backup_recent"
      interval_hours: 24
      max_age_hours: 48
```

### Health status

```bash
# Check health
curl http://localhost:8000/health

# Response:
{
  "status": "healthy",
  "version": "3.2.0",
  "uptime_seconds": 86400,
  "gpu": {"available": true, "device": "cuda", "memory_used_mb": 2048},
  "database": {"writable": true, "size_mb": 45},
  "disk": {"free_gb": 450}
}
```

### Health dashboard

```
Health Dashboard:
┌─────────────────────────────────────────┐
│  Status: ✅ Healthy                     │
│                                         │
│  Backend:    ✅ Running (24h)           │
│  Database:   ✅ Writable                │
│  GPU:        ✅ CUDA (RTX 4070)         │
│  Disk:       ✅ 450 GB free             │
│  Backup:     ✅ 2h ago                  │
│  Ollama:     ✅ Connected               │
│  Network:    ✅ Hub connected           │
│                                         │
│  Last check: 2026-09-19 12:00:00       │
└─────────────────────────────────────────┘
```

## Cleaning Procedures

### Cleanup types

```bash
# Cleanup thumbnails
muravei_env\Scripts\python.exe backend/scripts/cleanup.py --thumbnails

# Cleanup temp files
muravei_env\Scripts\python.exe backend/scripts/cleanup.py --temp

# Cleanup old backups
muravei_env\Scripts\python.exe backend/scripts/cleanup.py --backups --keep 10

# Cleanup all
muravei_env\Scripts\python.exe backend/scripts/cleanup.py --all
```

### Space savings

| Cleanup | Typical savings |
|---------|----------------|
| Thumbnails | 100-500 MB |
| Temp files | 50-200 MB |
| Old backups | 1-5 GB |
| Old logs | 200-500 MB |
| **Total** | **1.5-6.2 GB** |

## Maintenance Checklist

### Daily

```
Daily maintenance:
┌─────────────────────────────────────────┐
│  ☐ Backup completed                    │
│  ☐ Health check passed                 │
│  ☐ Disk space > 10 GB                  │
│  ☐ No critical errors in logs          │
│  ☐ GPU temperature < 80°C              │
└─────────────────────────────────────────┘
```

### Weekly

```
Weekly maintenance:
┌─────────────────────────────────────────┐
│  ☐ Database vacuum                     │
│  ☐ Cleanup old logs (>30 days)         │
│  ☐ Review health reports               │
│  ☐ Check backup integrity              │
│  ☐ Update incident log                 │
└─────────────────────────────────────────┘
```

### Monthly

```
Monthly maintenance:
┌─────────────────────────────────────────┐
│  ☐ Full database optimize              │
│  ☐ Review access logs                  │
│  ☐ Test restore from backup            │
│  ☐ Check for updates                   │
│  ☐ Hardware inspection (dust, fans)   │
│  ☐ Performance benchmarks              │
└─────────────────────────────────────────┘
```

## Troubleshooting

### Проблема: Backup не создаётся

```
Backup failed
Solution:
1. Проверьте disk space
2. Проверьте права доступа
3. Проверьте logs: data/logs/backup.log
4. Запустите вручную: backup.py --full
```

### Проблема: БД растёт слишком быстро

```
Database growing fast
Solution:
1. Проверьте size: db_size.py
2. VACUUM: db_vacuum.py
3. Cleanup old sessions
4. Increase retention policy
```

## Дальнейшие шаги

1. **[Diagnostics](./DIAGNOSTICS.md)** — диагностика
2. **[Updating](./UPDATING.md)** — обновление
3. **[Models](./MODELS.md)** — управление моделями

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
