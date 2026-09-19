# Начало работы — MuraveiVision PRO

> **Быстрый переход по ролям:**
> - [Оператор →](./OPERATOR_QUICKSTART.md)
> - [Инженер →](./ENGINEER_QUICKSTART.md)
> - [Разработчик →](./DEVELOPER_QUICKSTART.md)

## Что такое MuraveiVision PRO?

MuraveiVision PRO — профессиональная система анализа видеоданных для полевой работы, включающая:

- **Обнаружение объектов** — YOLO26 с SAHI-слайсингом для больших изображений
- **Интерактивная сегментация** — SAM3 (Segment Anything Model 3)
- **Пакетная обработка** — Batch Scan, Batch Segmentation, Change Detection
- **AI-анализ** — интеграция с Ollama для семантического анализа
- **3D-реконструкция** — COLMAP, DA3 (Depth Anything 3), GSplat, Flight3D
- **Сетевое взаимодействие** — обмен данными между узлами, чат, геолокация
- **Обучение моделей** — fine-tuning YOLO с resume checkpoint

## Системные требования

| Компонент | Минимум | Рекомендуется |
|-----------|---------|---------------|
| CPU | x64, 4 ядра | 8+ ядер |
| RAM | 8 GB | 16 GB+ |
| GPU | NVIDIA (CUDA 12.x) | RTX 3070+ (8GB VRAM) |
| Диск | 10 GB SSD | NVMe SSD 50 GB+ |
| ОС | Windows 10/11 | Windows 11 Pro |
| CUDA | 12.x | 12.4+ |

> **Air-gap режим:** MuraveiVision PRO работает полностью автономно. Все модели и зависимости должны быть загружены заранее.

## Быстрый старт

### 1. Развёртывание

```bash
# Клонирование репозитория
git clone https://github.com/nmuravev/MuraveiVision-PRO.git
cd MuraveiVision-PRO

# Создание окружения
python -m venv muravei_env
muravei_env\Scripts\activate

# Установка зависимостей (офлайн)
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Сборка фронтенда
cd MurVis
npm install
npm run build
cd ..

# Запуск
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 2. Первый запуск

1. Откройте `http://localhost:8000` в браузере
2. Загрузите медиафайл через панель «Media»
3. Запустите обнаружение через панель «Detection»
4. Просмотрите результаты на canvas

### 3. Проверка работоспособности

```bash
# Backend smoke test
muravei_env\Scripts\python.exe -m pytest backend/tests/smoke/ -q

# Frontend build check
cd MurVis && npm run build && cd ..
```

## Структура документации

```
docs/
├── 00-GETTING-STARTED/     ← Вы здесь
├── 01-OPERATOR/            ← Полевая работа
├── 02-ENGINEER/            ← Развёртывание и обслуживание
├── 03-DEVELOPER/           ← Разработка
├── 04-FEATURES/            ← Описание возможностей
├── 05-REFERENCE/           ← Справочные материалы
├── 06-SECURITY/            ← Безопасность
├── 07-RELEASES/            ← Релизы и миграция
├── GLOSSARY.md             ← Терминология
└── legacy/                 ← Архив документов
```

## Дальнейшие шаги

1. **Оператор:** начните с [Operator Quick Start](./OPERATOR_QUICKSTART.md)
2. **Инженер:** см. [Engineer Quick Start](./ENGINEER_QUICKSTART.md)
3. **Разработчик:** см. [Developer Quick Start](./DEVELOPER_QUICKSTART.md)
4. **Терминология:** [GLOSSARY.md](../GLOSSARY.md)
5. **Возможности:** [Features Overview](../04-FEATURES/OVERVIEW.md)

## Версия документации

- **Версия приложения:** v3.2.0
- **Дата:** 2026-09-19
- **Исправлено багов:** 40 (P0: 11, P1: 14, P2: 15)
