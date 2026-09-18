# Быстрый старт — Разработчик

> **Цель:** Настроить среду разработки, запустить тесты, внести первый вклад.

## Предварительные требования

- Windows 10/11 с административными правами
- Git установлен
- Python 3.10 — 3.12
- Node.js 18.x LTS
- VS Code (рекомендуется)

## Шаг 1: Настройка Git

### 1.1 Базовая конфигурация

```bash
# Проверка Git
git --version
# git version 2.43.0

# Базовая конфигурация
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
git config --global core.autocrlf true
git config --global core.safecrlf true
```

### 1.2 Клонирование репозитория

```bash
# С сетью
git clone https://github.com/nmuravev/MuraveiVision-PRO.git
cd MuraveiVision-PRO

# Без сети (из локального репозитория)
git clone \\server\shared\MuraveiVision-PRO.git
cd MuraveiVision-PRO
```

### 1.3 Git hooks (опционально)

```bash
# Установка pre-commit hooks
copy .githooks\pre-commit .git\hooks\pre-commit
copy .githooks\pre-push .git\hooks\pre-push

# Проверка
dir .git\hooks\
```

## Шаг 2: Настройка Python окружения

### 2.1 Создание venv

```bash
# Создание окружения
python -m venv muravei_env

# Активация
muravei_env\Scripts\activate

# Проверка
python --version
# Python 3.11.9

where python
# D:\LLM\MuraveiVision-PRO\muravei_env\Scripts\python.exe
```

### 2.2 Установка зависимостей

```bash
# С сетью
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Без сети
pip install --no-index --find-links=./offline-packages -r requirements.txt
pip install --no-index --find-links=./offline-packages -r requirements-dev.txt

# Проверка
pip check
# No broken requirements found
```

### 2.3 Установка dev-инструментов

```bash
# pytest
pip install pytest pytest-cov pytest-asyncio

# mypy (type checking)
pip install mypy types-all

# ruff (linting)
pip install ruff

# black (formatting)
pip install black

# Проверка
pytest --version
# pytest 8.3.0

mypy --version
# mypy 1.11.0
```

## Шаг 3: Настройка Frontend окружения

### 3.1 Установка Node.js

```bash
# Проверка
node --version
# v18.19.0

npm --version
# 10.2.4
```

### 3.2 Установка зависимостей

```bash
cd MurVis

# Установка
npm install

# Проверка
npm list --depth=0
# MurVis@3.2.0
# ├── react@18.3.1
# ├── react-dom@18.3.1
# ├── typescript@5.5.0
# ├── vite@5.4.0
# └── zustand@4.5.0
```

### 3.3 TypeScript конфигурация

```bash
# Проверка TypeScript
npx tsc --version
# Version 5.5.0

# Тип-чек без сборки
npx tsc --noEmit
# output: Found 0 errors.
```

## Шаг 4: Запуск development серверов

### 4.1 Backend (dev mode)

```bash
# Активация окружения
muravei_env\Scripts\activate

# Запуск с auto-reload
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level debug

# Output:
# INFO:     Will watch for changes to source directories: backend
# INFO:     Uvicorn running on http://0.0.0.0:8000
# INFO:     Application startup complete.
```

### 4.2 Frontend (dev mode)

```bash
cd MurVis

# Запуск Vite dev server
npm run dev

# Output:
#   VITE v5.0.12  ready in 450 ms
#   ➜  Local:   http://localhost:5173/
#   ➜  Network: http://192.168.1.100:5173/
#   ➜  press h + enter to show help
```

### 4.3 Проверка подключения

```bash
# Backend health
curl http://localhost:8000/health
# {"status": "ok", "version": "3.2.0", "gpu": "cuda"}

# Frontend
# Откройте http://localhost:5173
# Должна загрузиться страница входа
```

## Шаг 5: Тестирование

### 5.1 Backend тесты

```bash
# Все тесты (кроме load)
cd /d D:\LLM\MuraveiVision-PRO
set "PYTHONPATH=backend"
muravei_env\Scripts\python.exe -m pytest backend/tests/ -q --ignore=backend/tests/load_test.py

# Output:
# 360 passed in 45.23s

# Только smoke тесты
muravei_env\Scripts\python.exe -m pytest backend/tests/smoke/ -q

# Только unit тесты
muravei_env\Scripts\python.exe -m pytest backend/tests/unit/ -q

# С покрытием
muravei_env\Scripts\python.exe -m pytest backend/tests/ --cov=backend --cov-report=html -q
```

### 5.2 Frontend тесты

```bash
cd MurVis

# Все тесты
npm run test

# В watch режиме
npm run test -- --watch

# С покрытием
npm run test -- --coverage
```

### 5.3 E2E тесты

```bash
# Запуск E2E тестов
muravei_env\Scripts\python.exe -m pytest backend/tests/e2e/ -q --tb=short

# Smoke тесты
muravei_env\Scripts\python.exe -m pytest backend/tests/smoke/ -q
```

## Шаг 6: Код-стайл и линтинг

### 6.1 Python linting

```bash
# Ruff (linting)
ruff check backend/

# Ruff (formatting)
ruff format backend/

# Black (альтернатива)
black backend/

# mypy (type checking)
mypy backend/ --ignore-missing-imports
```

### 6.2 TypeScript linting

```bash
cd MurVis

# TypeScript type check
npx tsc --noEmit

# ESLint
npx eslint src/

# Prettier check
npx prettier --check src/
```

### 6.3 Pre-commit проверки

```bash
# Полный чек перед коммитом
cd /d D:\LLM\MuraveiVision-PRO

# Backend
set "PYTHONPATH=backend"
muravei_env\Scripts\python.exe -m py_compile backend/main.py
muravei_env\Scripts\python.exe -m py_compile backend/api/

# Frontend
cd MurVis
npx tsc --noEmit
npm run lint
cd ..
```

## Шаг 7: Отладка

### 7.1 Python debugger

```bash
# Запуск с debugger
muravei_env\Scripts\python.exe -m pdb backend/main.py

# Или через VS Code:
# 1. Откройте backend/main.py
# 2. Поставьте breakpoint (F9)
# 3. Launch configuration: "Python: Current File"
# 4. F5 для запуска
```

### 7.2 Frontend debugger

```bash
# VS Code Chrome Debugger:
# 1. Установите расширение "Debugger for Chrome"
# 2. Launch configuration:
#    {
#      "type": "chrome",
#      "request": "launch",
#      "url": "http://localhost:5173",
#      "webRoot": "${workspaceFolder}/MurVis/src"
#    }
# 3. F5 для запуска
```

### 7.3 WebSocket debugging

```python
# Включение WebSocket debug логирования
# config/custom.yaml
logging:
  level: DEBUG
  websocket: true
  log_file: data/logs/websocket.log
```

## Шаг 8: Вклад в проект

### 8.1 Git workflow

```bash
# Создание ветки
git checkout -b feature/your-feature-name

# Разработка
# ...

# Проверка
git status
git diff

# Коммит (conventional commits)
echo "feat: add your feature description" > .commit_msg.txt
git add your_file.py
git commit -F .commit_msg.txt

# Push
git push origin feature/your-feature-name
```

### 8.2 Conventional commits

```
feat: add new detection model
fix: resolve WebSocket reconnection issue
docs: update API reference
refactor: simplify database queries
test: add unit tests for utils
chore: update dependencies
```

### 8.3 Code review checklist

- [ ] Tests pass (`pytest backend/tests/ -q --ignore=backend/tests/load_test.py`)
- [ ] TypeScript check (`npx tsc --noEmit`)
- [ ] Linting (`ruff check`, `eslint`)
- [ ] No debug code left (`print()`, `console.log()`)
- [ ] No hardcoded secrets
- [ ] Air-gap compatible (no runtime downloads)
- [ ] Documentation updated

## Troubleshooting

### Проблема: Тесты не проходят

```
Error: FAILED test_something.py::test_case
Solution:
1. Запустите с подробным выводом: pytest -v
2. Проверьте traceback
3. Проверьте зависимости: pip check
4. Проверьте БД: SQLite WAL mode enabled?
```

### Проблема: TypeScript ошибки

```
Error: TS2322: Type 'X' is not assignable to type 'Y'
Solution:
1. Проверьте типы в ошибке
2. Проверьте interfaces в соответствующих .d.ts файлах
3. Запустите: npx tsc --noEmit --pretty
```

### Проблема: Backend не перезапускается

```
Error: Address already in use
Solution:
1. Найдите процесс: netstat -ano | findstr :8000
2. Убейте процесс: taskkill /PID <PID> /F
3. Перезапустите backend
```

## Дальнейшие шаги

1. **[Архитектура](../03-DEVELOPER/ARCHITECTURE.md)** — изучите архитектуру
2. **[API Reference](../03-DEVELOPER/API_REFERENCE.md)** — все endpoints
3. **[База данных](../03-DEVELOPER/DATABASE.md)** — schema и миграции
4. **[Тестирование](../03-DEVELOPER/TESTING.md)** — стратегии тестирования
5. **[Вклад в проект](../03-DEVELOPER/CONTRIBUTING.md)** — guidelines

## Поддержка

- **Документация:** [GLOSSARY.md](../GLOSSARY.md)
- **Архитектура:** [Architecture](../03-DEVELOPER/ARCHITECTURE.md)
- **GitHub:** [Issues](https://github.com/nmuravev/MuraveiVision-PRO/issues)
