# Разработчик — MuraveiVision PRO

> **Руководство для разработчиков: архитектура, API, тестирование, вклад в проект.**

## Введение

Это руководство для разработчиков — специалистов, которые создают и поддерживают MuraveiVision PRO.

## Основные разделы

| Раздел | Описание | Документация |
|--------|----------|--------------|
| **Architecture** | Компоненты, data flow, state | [Architecture](./ARCHITECTURE.md) |
| **API Reference** | Все endpoints с curl | [API Reference](./API_REFERENCE.md) |
| **Database** | Schema, миграции, WAL | [Database](./DATABASE.md) |
| **Testing** | Unit, E2E, smoke, field | [Testing](./TESTING.md) |
| **Contributing** | Git, code review, air-gap | [Contributing](./CONTRIBUTING.md) |
| **Debugging** | Python, React, WebSocket | [Debugging](./DEBUGGING.md) |

## Стек технологий

| Слой | Технология | Версия |
|------|-----------|--------|
| **Backend** | FastAPI + Uvicorn | 0.115+ |
| **ML** | PyTorch + SAHI | 2.4+ |
| **Database** | SQLite (WAL) | 3.45+ |
| **Frontend** | React + TypeScript + Vite | 18.3+ |
| **State** | Zustand | 4.5+ |
| **AI** | Ollama | 0.2+ |
| **Build** | npm | 10.2+ |

## Структура проекта

```
MuraveiVision-PRO/
├── backend/                    # Backend application
│   ├── main.py                # FastAPI app entry
│   ├── api/                   # API routers
│   │   ├── detection.py       # Detection endpoints
│   │   ├── segmentation.py    # Segmentation endpoints
│   │   ├── ai.py              # AI analysis endpoints
│   │   └── network.py         # Network endpoints
│   ├── models/                # Model wrappers
│   │   ├── yolo.py           # YOLO inference
│   │   ├── sam3.py           # SAM3 segmentation
│   │   └── da3.py            # DA3 depth
│   ├── services/              # Business logic
│   │   ├── detection_service.py
│   │   ├── session_service.py
│   │   └── backup_service.py
│   ├── schemas/               # Pydantic models
│   ├── utils/                 # Utilities
│   ├── tests/                 # Tests
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── e2e/
│   │   └── smoke/
│   └── scripts/               # Utility scripts
├── MurVis/                    # Frontend application
│   ├── src/
│   │   ├── components/       # React components
│   │   ├── store/            # Zustand stores
│   │   ├── hooks/            # Custom hooks
│   │   ├── api/              # API client
│   │   └── types/            # TypeScript types
│   └── dist/                 # Built output
├── config/                    # Configuration files
├── docs/                      # Documentation
├── data/                      # Runtime data
│   ├── muravei.db            # SQLite database
│   ├── logs/                 # Application logs
│   └── backups/              # Backups
└── tests/                     # Integration tests
```

## Быстрый старт разработчика

```bash
# 1. Clone
git clone https://github.com/nmuravev/MuraveiVision-PRO.git
cd MuraveiVision-PRO

# 2. Backend
python -m venv muravei_env
muravei_env\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. Frontend
cd MurVis
npm install
npm run build
cd ..

# 4. Database
muravei_env\Scripts\python.exe backend/scripts/init_db.py

# 5. Run backend
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 6. Run frontend (separate terminal)
cd MurVis
npm run dev
```

## Code Standards

### Python

```bash
# Linting
ruff check backend/

# Formatting
ruff format backend/

# Type checking
mypy backend/ --ignore-missing-imports

# Tests
muravei_env\Scripts\python.exe -m pytest backend/tests/ -q --ignore=backend/tests/load_test.py
```

### TypeScript

```bash
cd MurVis

# Type checking
npx tsc --noEmit

# Linting
npx eslint src/

# Formatting
npx prettier --check src/
```

## Git Discipline

### Conventional commits

```
feat: add DA3 dense backend
fix: resolve WebSocket reconnection
docs: update API reference
refactor: simplify detection service
test: add unit tests for backup
chore: update dependencies
```

### Branch naming

```
feature/da3-backend
fix/websocket-reconnect
docs/api-reference
refactor/detection-service
```

### PR checklist

- [ ] Tests pass
- [ ] TypeScript check passes
- [ ] Linting passes
- [ ] No debug code
- [ ] No hardcoded secrets
- [ ] Air-gap compatible
- [ ] Documentation updated

## Дальнейшие шаги

1. **[Architecture](./ARCHITECTURE.md)** — изучите архитектуру
2. **[API Reference](./API_REFERENCE.md)** — все endpoints
3. **[Testing](./TESTING.md)** — стратегии тестирования
4. **[Contributing](./CONTRIBUTING.md)** — guidelines

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
