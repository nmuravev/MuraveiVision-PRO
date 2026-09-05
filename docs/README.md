# Документация MuraveiVision PRO

Единая папка проектной документации. Корневой [`README.md`](../README.md) — краткий вход; детали здесь.

**Источник истины для AI-агентов** (читать по порядку, см. [`AGENTS.md`](../AGENTS.md)):
[`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) → [`ARCHITECTURE.md`](ARCHITECTURE.md) → [`DEVELOPMENT.md`](DEVELOPMENT.md) → [`MASTER_PLAN.md`](MASTER_PLAN.md).

| Документ | Для кого | Содержание |
|----------|----------|------------|
| [MASTER_PLAN.md](MASTER_PLAN.md) | Продукт / инженеры / ИИ | Сводка статуса, инварианты, backlog, правила auto-sync docs |
| [DOCS_SYNC_CHECKLIST.md](DOCS_SYNC_CHECKLIST.md) | Все | Чеклист синхронизации документации после изменений |
| [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) | ИИ-агенты, новые разработчики | Паспорт проекта: стек, дерево, запреты, быстрый ориентир |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Инженеры + ИИ-агенты | Слои, потоки, UI mosaic (часть A) и инварианты air-gap / detect≠seg (часть B) |
| [ARCHITECTURE_FOR_AI.md](ARCHITECTURE_FOR_AI.md) | ИИ-агенты | Stub → [ARCHITECTURE.md](ARCHITECTURE.md) |
| [DIRECTORY_STRUCTURE.md](DIRECTORY_STRUCTURE.md) | Все | Актуальная топография репозитория |
| [API.md](API.md) | Frontend / интеграция | REST + WebSocket эндпоинты (вкл. SAHI, Response Validator) |
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | Инженеры / ML | 11 таблиц SQLite, индексы, миграции |
| [CONFIGURATION.md](CONFIGURATION.md) | Инженеры | SQLite settings, константы YOLO/SAHI/валидатор, сеть, классы, env |
| [DETECTION_AND_TRAINING.md](DETECTION_AND_TRAINING.md) | ML / оператор обучения | YOLO/YOLOE, классы 238, дообучение, CUDA |
| [RECON_3D.md](RECON_3D.md) | Инженеры / оператор | COLMAP/gsplat/AliceVision, реконструкция, Flight3D, raycast |
| [ALICEVISION.md](ALICEVISION.md) | Инженеры / оператор | Dense MVS / mesh sidecar, пресеты, CUDA, portable |
| [ATTRIBUTION.md](ATTRIBUTION.md) | Юристы / релиз | AliceVision MPL-2.0 и сторонние лицензии |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Сборка / поле | Развёртывание с нуля, portable, troubleshooting |
| [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md) | Сборка / поле | Offline env pack (wheels): make_env_pack / setup_env |
| [PORTABLE.md](PORTABLE.md) | Сборка / поле | Portable ZIP, embeddable Python, состав комплекта |
| [FEATURES.md](FEATURES.md) | Все | Что реализовано (с примерами использования) |
| [KNOWN_ISSUES.md](KNOWN_ISSUES.md) | Все | Ограничения, flaky-зоны, вне скоупа |
| [ERROR_REFERENCE.md](ERROR_REFERENCE.md) | Оператор / инженер | HTTP-ошибки: причины, решения, полевой справочник |
| [TODO.md](TODO.md) | Продукт / инженеры | Приоритизированный план оставшейся работы |
| [ROADMAP.md](ROADMAP.md) | Продукт | Бэклог P0–P3, 3D-траектория, Full Kit |
| [PHASE4_RETRO.md](PHASE4_RETRO.md) | Продукт / инженеры | Sprint notes P3.13/P3.15 |
| [PHASE3_FINAL_RETRO.md](PHASE3_FINAL_RETRO.md) | Продукт / инженеры | Финальная ретроспектива Phase 3 / P3 |
| [TESTING.md](TESTING.md) | Все | Запуск тестов (Playwright + unittest + SAHI + build) |
| [SMOKE_TESTS.md](SMOKE_TESTS.md) | Все | Инвентарь smoke-скриптов |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Разработчики | Окружение Python 3.12, запуск, smoke, правила |
| [OPERATOR_GUIDE.md](OPERATOR_GUIDE.md) | Оператор | Полевая работа: съёмка/стрим, разметка, фиксация, цели |
| [ANALYST_GUIDE.md](ANALYST_GUIDE.md) | Аналитик | Проверка/правка детекций, отчёты, экспорт, Active Learning |
| [ENGINEER_GUIDE.md](ENGINEER_GUIDE.md) | Инженер | Установка, настройка, модели, сеть, диагностика, обслуживание |

Устаревшие манифесты из `.backup/MuraveiVision/*.md` **не использовать** — они описывают другой каркас (ONNX-only, Mini/Pro, фантомные пути).
