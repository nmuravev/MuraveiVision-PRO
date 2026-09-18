# Updating — MuraveiVision PRO

> **Обновление версий, миграции, rollback procedures.**

## Обзор

Обновление MuraveiVision PRO включает: git pull, переустановку зависимостей, пересборку frontend, миграцию БД, обновление конфигурации.

## Upgrade Procedures

### Minor update (v3.2.0 → v3.2.1)

```bash
# Pre-update checklist
┌─────────────────────────────────────────┐
│  ☐ Backup database                      │
│  ☐ Note current version                 │
│  ☐ Review changelog                     │
│  ☐ Test in dev environment first       │
│  ☐ Notify users of downtime            │
│  ☐ Have rollback plan ready            │
└─────────────────────────────────────────┘

# Update process
git fetch origin
git pull origin v3.2.1

muravei_env\Scripts\activate
pip install -r requirements.txt

cd MurVis
npm install
npm run build
cd ..

muravei_env\Scripts\python.exe backend/scripts/migrate_db.py

muravei_env\Scripts\python.exe backend/scripts/diagnose.py
```

### Major update (v3.1.x → v3.2.0)

```bash
# Additional steps for major update:

# 1. Check breaking changes in changelog
# 2. Backup everything (DB, models, config)
# 3. Review new config parameters
# 4. Update custom.yaml for new params
# 5. Download new models (if any)
# 6. Test in isolated environment

# Example: v3.1 → v3.2
git fetch origin
git checkout v3.2.0

# New dependencies for DA3
pip install -r requirements.txt

# New models for DA3
muravei_env\Scripts\python.exe backend/scripts/download_models.py da3

# Config migration
python backend/scripts/migrate_config.py --from 3.1 --to 3.2

# DB migration
muravei_env\Scripts\python.exe backend/scripts/migrate_db.py
```

## Git Workflow

### Pull and rebuild

```bash
# Check current version
git describe --tags

# Fetch latest
git fetch origin

# List available versions
git tag --list 'v3.*' | sort -V

# Pull specific version
git checkout v3.2.0

# Or pull latest main
git pull origin main
```

### Rebuild frontend

```bash
cd MurVis

# Clean install
rm -rf node_modules
npm install

# Build
npm run build

# Verify
dir dist\
# Should show index.html, assets/

cd ..
```

## Database Migration

### Auto migration

```bash
# Run migrations
muravei_env\Scripts\python.exe backend/scripts/migrate_db.py

# Output:
# [OK] Current version: 3.1.0
# [OK] Target version: 3.2.0
# [OK] Applying migration: add_da3_tables
# [OK] Applying migration: add_session_trace
# [OK] Database migrated to v3.2.0
# [OK] Migration time: 2.3s
```

### Migration history

| Version | Date | Changes |
|---------|------|---------|
| **3.0.0** | 2026-06-01 | Initial schema |
| **3.1.0** | 2026-08-01 | Add network tables |
| **3.2.0** | 2026-09-19 | Add DA3 tables, session trace |

### Rollback migration

```bash
# ⚠️ Rollback only if necessary
# Backup first!
muravei_env\Scripts\python.exe backend/scripts/backup.py --full

# Rollback (if available)
muravei_env\Scripts\python.exe backend/scripts/migrate_db.py --rollback
```

## Configuration Migration

### Config changes by version

```yaml
# v3.1.0 config
database:
  url: sqlite:///data/muravei.db
  wal_mode: true

# v3.2.0 config (NEW params)
database:
  url: sqlite:///data/muravei.db
  wal_mode: true
  auto_vacuum:              # ← NEW
    enabled: true
    interval_days: 7

gpu:
  device: cuda
  memory_fraction: 0.8     # ← NEW

network:
  ws_channels:             # ← NEW
    n1: "status"
    n2: "detections"
```

### Auto migration tool

```bash
# Migrate config automatically
python backend/scripts/migrate_config.py \
  --from 3.1 --to 3.2 \
  --input config/custom.yaml \
  --output config/custom_v3.2.yaml

# Output:
# [OK] Read config: config/custom.yaml
# [OK] Added 3 new sections
# [OK] Deprecated 2 old params
# [OK] Written: config/custom_v3.2.yaml
# [OK] Review and update values
```

## Model Updates

### Download new models

```bash
# Update all models
muravei_env\Scripts\python.exe backend/scripts/update_models.py

# Update specific model
muravei_env\Scripts\python.exe backend/scripts/update_models.py \
  --model yolo8s

# Update DA3 (new in v3.2.0)
muravei_env\Scripts\python.exe backend/scripts/update_models.py \
  --model da3
```

### Model versioning

```
Model versions:
┌─────────────────────────────────────────┐
│  yolo8s-ft:                             │
│  • v1.0 (2026-06) — initial             │
│  • v2.0 (2026-08) — improved classes   │
│  • v3.0 (2026-09) — current            │
│                                         │
│  sam3:                                  │
│  • v1.0 (2026-07) — initial             │
│  • v1.1 (2026-09) — current            │
│                                         │
│  da3:                                   │
│  • v1.0 (2026-09) — new in v3.2.0     │
└─────────────────────────────────────────┘
```

## Rollback Procedures

### Full rollback

```bash
# 1. Stop backend
# Ctrl+C or: net stop MuraveiVision

# 2. Restore database
copy data\backups\muravei_before_update.db data\muravei.db

# 3. Checkout previous version
git checkout v3.1.0

# 4. Restore dependencies
pip install -r requirements.txt

# 5. Restore frontend
cd MurVis
git checkout v3.1.0
npm install
npm run build
cd ..

# 6. Restore config
copy config\custom_before.yaml config\custom.yaml

# 7. Start backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Partial rollback (config only)

```bash
# Restore previous config
copy config\custom_v3.1.yaml config\custom.yaml

# Restart backend
# Ctrl+C
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Post-update Verification

### Verification checklist

```
Post-update checklist:
┌─────────────────────────────────────────┐
│  ☐ Backend starts without errors       │
│  ☐ Frontend builds successfully        │
│  ☐ Health endpoint responds            │
│  ☐ Database migration completed        │
│  ☐ GPU detected and working            │
│  ☐ Models loaded successfully          │
│  ☐ Smoke tests pass                    │
│  ☐ Configuration valid                 │
│  ☐ Backup working                      │
│  ☐ Network connections established     │
│  ☐ Users can login                     │
│  ☐ Detection works on test image       │
└─────────────────────────────────────────┘
```

### Automated verification

```bash
# Run all checks
muravei_env\Scripts\python.exe backend/scripts/diagnose.py
muravei_env\Scripts\python.exe -m pytest backend/tests/smoke/ -q
curl http://localhost:8000/health
```

## Troubleshooting

### Проблема: Migration fails

```
Migration failed
Solution:
1. Check logs: data/logs/app.log
2. Backup database immediately
3. Try rollback
4. Check DB integrity: db_check.py
5. Contact support
```

### Проблема: Backend не запускается после update

```
Backend won't start
Solution:
1. Check requirements: pip install -r requirements.txt
2. Check config: custom.yaml valid YAML?
3. Check logs: data/logs/error.log
4. Try rollback to previous version
```

## Дальнейшие шаги

1. **[Models](./MODELS.md)** — управление моделями
2. **[Maintenance](./MAINTENANCE.md)** — обслуживание
3. **[Diagnostics](./DIAGNOSTICS.md)** — диагностика

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
