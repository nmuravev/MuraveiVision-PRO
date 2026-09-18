# Legacy Documentation — MuraveiVision PRO

> **Архив старых документов.**

## Обзор

Этот каталог содержит архивные документы, которые были заменены или обновлены в новых версиях документации.

## Категории

### Planning

| Файл | Описание | Статус |
|------|----------|--------|
| **MASTER_PLAN.md** | Главный план проекта | ← заменён INDEX.md |
| **ROADMAP.md** | Roadmap развития | Архив |
| **TODO.md** | Текущие задачи | ← см. GitHub Issues |

### Retrospectives

| Файл | Описание |
|------|----------|
| **PHASE3_FINAL_RETRO.md** | Ретроспектива Phase 3 |
| **PHASE4_RETRO.md** | Ретроспектива Phase 4 |

### Proposals & Specs

| Файл | Описание |
|------|----------|
| **STUDIO_PROPOSAL.md** | Proposal для studio |
| **SPEC_FIELD_MACBOOK.md** | Field specs для MacBook |
| **PROJECT_CONTEXT.md** | Context проекта |

### Skills

| Файл | Описание |
|------|----------|
| **SKILL_CODEX.md** | Skill codex |
| **SKILL_QWEN_LOCAL.md** | Qwen local skill |

### Technical Notes

| Файл | Описание |
|------|----------|
| **ALICEVISION.md** | AliceVision notes |
| **ARCHITECTURE_FOR_AI.md** | Architecture for AI |
| **ATTRIBUTION.md** | Attribution |
| **KNOWN_ISSUES.md** | Known issues |
| **DOCS_SYNC_CHECKLIST.md** | Docs sync checklist |

### Old Guides (replaced)

| Файл | Заменён на |
|------|-----------|
| **OPERATOR_GUIDE.md** | 01-OPERATOR/*.md |
| **ENGINEER_GUIDE.md** | 02-ENGINEER/*.md |
| **DEVELOPMENT.md** | 03-DEVELOPER/*.md |
| **DEPLOYMENT.md** | 02-ENGINEER/DEPLOYMENT.md |
| **CONFIGURATION.md** | 02-ENGINEER/CONFIGURATION.md |
| **FEATURES.md** | 04-FEATURES/OVERVIEW.md |
| **API.md** | 03-DEVELOPER/API_REFERENCE.md |
| **ERROR_REFERENCE.md** | 05-REFERENCE/ERROR_REFERENCE.md |
| **DATABASE_SCHEMA.md** | 05-REFERENCE/DATABASE_SCHEMA.md |
| **DIRECTORY_STRUCTURE.md** | 05-REFERENCE/DIRECTORY_STRUCTURE.md |
| **TESTING.md** | 03-DEVELOPER/TESTING.md |
| **DETECTION_AND_TRAINING.md** | 01-OPERATOR/DETECTION.md |
| **RECON_3D.md** | 04-FEATURES/RECON_3D.md |
| **NETWORK_REPLICATION.md** | 01-OPERATOR/NETWORK.md |
| **PORTABLE_GUIDE.md** | 02-ENGINEER/DEPLOYMENT.md |
| **PORTABLE.md** | 04-FEATURES/PORTABLE.md |
| **SMOKE_TESTS.md** | 02-ENGINEER/DIAGNOSTICS.md |
| **SMOKE_TEST_RESULTS.md** | Архив |

## Migration Guide

### От старых документов к новым

```
Старый документ          →    Новый документ
─────────────────────────────────────────────────
OPERATOR_GUIDE.md       →    01-OPERATOR/OVERVIEW.md
ENGINEER_GUIDE.md       →    02-ENGINEER/OVERVIEW.md
DEVELOPMENT.md          →    03-DEVELOPER/OVERVIEW.md
DEPLOYMENT.md           →    02-ENGINEER/DEPLOYMENT.md
CONFIGURATION.md        →    02-ENGINEER/CONFIGURATION.md
FEATURES.md             →    04-FEATURES/OVERVIEW.md
API.md                  →    03-DEVELOPER/API_REFERENCE.md
DATABASE_SCHEMA.md      →    05-REFERENCE/DATABASE_SCHEMA.md
TESTING.md              →    03-DEVELOPER/TESTING.md
MASTER_PLAN.md          →    docs/INDEX.md
```

## Почему архив?

1. **Новая структура** — MkDocs с role-based навигацией
2. **Обновлённый контент** — v3.2.0 изменения
3. **DA3 Dense Backend** — новая глава
4. **40 security fixes** — P0/P1/P2 секция
5. **Улучшенная навигация** — INDEX.md + GLOSSARY.md

## Доступ

Эти документы сохранены для исторической ценности и отладки старых версий.

Для актуальной информации см.:
- **[INDEX.md](../INDEX.md)** — unified navigation
- **[GLOSSARY.md](../GLOSSARY.md)** — terminology
- **01-OPERATOR/** — operator guide
- **02-ENGINEER/** — engineer guide
- **03-DEVELOPER/** — developer guide

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
