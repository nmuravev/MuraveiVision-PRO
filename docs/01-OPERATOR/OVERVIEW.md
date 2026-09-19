# Оператор — MuraveiVision PRO

> **Руководство для оператора:** полевая работа с медиа, обнаружение, сегментация, пакетная обработка, AI-анализ.

## Введение

Это руководство предназначено для операторов — пользователей, которые работают с MuraveiVision PRO в полевых условиях для анализа видеоданных.

## Основные возможности

| Возможность | Описание | Документация |
|-------------|----------|--------------|
| **Media Workflow** | Загрузка, просмотр, GPS sidecars | [Media Workflow](./MEDIA_WORKFLOW.md) |
| **Detection** | YOLO26 с SAHI-слайсингом | [Detection](./DETECTION.md) |
| **Segmentation** | SAM3 interactive & propagate | [Segmentation](./SEGMENTATION.md) |
| **Batch Scan** | Пакетная обработка видео | [Batch Scan](./BATCH_SCAN.md) |
| **Change Detection** | Сравнение "до/после" | [Change Detection](./CHANGE_DETECTION.md) |
| **AI Analysis** | Ollama rules & alerts | [AI Analysis](./AI_ANALYSIS.md) |
| **Training** | Fine-tuning моделей | [Training](./TRAINING.md) |
| **3D Reconstruction** | COLMAP, DA3, GSplat | [Reconstruction](./RECONSTRUCTION.md) |
| **Network** | Обмен данными между узлами | [Network](./NETWORK.md) |
| **Troubleshooting** | Устранение неполадок | [Troubleshooting](./TROUBLESHOOTING.md) |

## Рабочий процесс оператора

```
Загрузка медиа
    ↓
Предварительный просмотр
    ↓
Обнаружение (YOLO/SAHI)
    ↓
Сегментация (SAM3) — опционально
    ↓
Пакетная обработка — опционально
    ↓
AI-анализ (Ollama) — опционально
    ↓
3D-реконструкция — опционально
    ↓
Экспорт результатов
```

## Горячие клавиши

| Клавиша | Действие |
|---------|----------|
| `Space` | Play/Pause видео |
| `←` `→` | Предыдущий/следующий кадр |
| `+` `-` | Zoom in/out |
| `R` | Reset view |
| `E` | Export results |
| `D` | Toggle detection overlay |
| `S` | Toggle segmentation masks |
| `M` | Toggle metrics panel |
| `F` | Fullscreen |

## Советы по эффективности

### Для быстрых сессий

1. Используйте пресеты моделей (YOLO26n для скорости, YOLO26s для точности)
2. SAHI slice 512×512 для стандартных изображений
3. Batch Scan для папок с изображениями
4. Экспорт в CSV для быстрой обработки в Excel

### Для детального анализа

1. Запустите detection для общего обзора
2. Используйте SAM3 interactive для точных масок
3. Propagate сегментацию на видео
4. Запустите AI-анализ для семантики
5. Экспортируйте в COCO для публикации

## Часто задаваемые вопросы

**Q: Какая модель лучше для полевых условий?**
A: YOLO26n-ft для скорости, YOLO26s-ft для точности. Для сложных условий — fine-tune на ваших данных.

**Q: Почему detection работает медленно?**
A: Проверьте VRAM, уменьшите SAHI slice size, уменьшите batch size.

**Q: Как экспортировать результаты?**
A: Панель Results → Export → выберите формат (CSV, JSON, YOLO, COCO).

**Q: Можно ли работать без GPU?**
A: Да, но значительно медленнее. DA3 dense требует GPU.

## Связанные разделы

- **[Начало работы](../00-GETTING-STARTED/OVERVIEW.md)** — общий обзор
- **[Operator Quick Start](../00-GETTING-STARTED/OPERATOR_QUICKSTART.md)** — быстрый старт
- **[Терминология](../GLOSSARY.md)** — glossary терминов
- **[Возможности](../04-FEATURES/OVERVIEW.md)** — описание функций
- **[Устранение неполадок](../01-OPERATOR/TROUBLESHOOTING.md)** — troubleshooting

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
- **Исправлено багов:** 40 (P0: 11, P1: 14, P2: 15)
