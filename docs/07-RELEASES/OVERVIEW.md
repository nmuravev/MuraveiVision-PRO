# Релизы — MuraveiVision PRO

> **История релизов, обновление, миграция.**

## Обзор

MuraveiVision PRO следует semantic versioning (major.minor.patch).

## Version History

| Version | Date | Type | Fixes | Notes |
|---------|------|------|-------|-------|
| **v3.0.0** | 2026-06-01 | Major | 20 | Initial release |
| **v3.1.0** | 2026-08-01 | Minor | 5 | Network v3.3 prep |
| **v3.2.0** | 2026-09-19 | Minor | 40 | DA3 + all P0/P1/P2 fixes |

## v3.2.0 Highlights

### New Features

- **DA3 Dense Backend** — Depth Anything 3 support (4 variants)
- **Session trace** — detailed session logging
- **Enhanced batch operations** — improved performance

### Security Fixes

- **40 total fixes:** P0: 11, P1: 14, P2: 15
- **RCE prevention** — pickle → msgpack
- **SQL injection** — whitelist queries
- **Prompt injection** — DATA wrapping

### Bug Fixes

- WebSocket stabilization
- State management fixes (Zustand selectors)
- Closure stale refs
- Lock NAT support
- Export KeyError fixes

## Upgrade Guide

### v3.1 → v3.2

```bash
# 1. Backup
muravei_env\Scripts\python.exe backend/scripts/backup.py --full

# 2. Update
git checkout v3.2.0
pip install -r requirements.txt

# 3. New models
muravei_env\Scripts\python.exe backend/scripts/download_models.py da3

# 4. Migrate
muravei_env\Scripts\python.exe backend/scripts/migrate_db.py

# 5. Verify
muravei_env\Scripts\python.exe backend/scripts/diagnose.py
```

## Support Policy

### Lifecycle

```
Version support:
v3.2.x — ✅ Supported (current)
v3.1.x — ⚠️ Security fixes only
v3.0.x — ❌ End of life
```

### Release schedule

| Type | Frequency | Examples |
|------|-----------|----------|
| **Patch** | As needed | Bug fixes |
| **Minor** | Quarterly | New features, backward compatible |
| **Major** | Annual | Breaking changes |

## Дальнейшие шаги

1. **[Changelog](../CHANGELOG.md)** — полная история
2. **[v3.2.0](./V3.2.0.md)** — детали релиза
3. **[Migration](./MIGRATION_GUIDE.md)** — руководство по миграции

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
