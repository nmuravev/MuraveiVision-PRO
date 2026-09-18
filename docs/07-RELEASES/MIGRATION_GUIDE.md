# Migration Guide — MuraveiVision PRO

> **Руководство по миграции между версиями.**

## v3.1 → v3.2

### Breaking Changes

- New DA3 models required
- New database tables (session_trace)
- Updated configuration schema

### Migration Steps

```bash
# 1. Backup
python backend/scripts/backup.py --full

# 2. Update code
git checkout v3.2.0

# 3. Install dependencies
pip install -r requirements.txt

# 4. Download new models
python backend/scripts/download_models.py da3

# 5. Migrate database
python backend/scripts/migrate_db.py

# 6. Update config
python backend/scripts/migrate_config.py --from 3.1 --to 3.2

# 7. Verify
python backend/scripts/diagnose.py
```

### Configuration Changes

New keys in v3.2.0:
- `database.auto_vacuum`
- `gpu.memory_fraction`
- `network.ws_channels`

## Версия

- **Приложение:** v3.2.0
