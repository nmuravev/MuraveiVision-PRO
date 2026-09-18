# Segmentation — MuraveiVision PRO

> **Интерактивная и propagate сегментация с помощью SAM3.**

## Обзор

Segmentation — система точной сегментации объектов с использованием SAM3 (Segment Anything Model 3). Поддерживает interactive mode (ручная разметка) и propagate mode (автоматическое распространение на видео).

## Архитектура сегментации

```
Segmentation Pipeline:
┌──────────────────┐
│  Detection Result │ (optional input)
└───────┬──────────┘
        │
        ▼
┌──────────────────┐     ┌──────────────────┐
│  User Input       │     │  Auto-mask from  │
│  • Point          │     │  Detection       │
│  • Rectangle      │     │  (bbox)          │
│  • Polygon        │     └────────┬─────────┘
│  • Freehand       │              │
└───────┬──────────┘              │
        │                         │
        ▼                         ▼
┌─────────────────────────────────────────┐
│         SAM3 Model Inference            │
│  • Segment Anything Model 3             │
│  • GPU acceleration (CUDA)              │
│  • Mask generation                      │
└───────┬─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  Mask Post-processing                   │
│  • Edge refinement                     │
│  • Hole filling                        │
│  • Size filtering                      │
└───────┬─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  Results                                │
│  • Binary mask (PNG)                   │
│  • Polygon outline                     │
│  • Contour points                      │
│  • Area (pixels, cm²)                 │
└─────────────────────────────────────────┘
```

## Режимы сегментации

### Interactive Mode

Ручная разметка объектов на изображении.

```
Interactive Segmentation:
┌─────────────────────────────────────────┐
│  Mode: [Interactive ▼]                  │
│                                         │
│  Tools:                                 │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐      │
│  │👆   │ │▭    │ │⬡    │ │✏    │      │
│  │Point│ │Rect │ │Poly │ │Free │      │
│  └─────┘ └─────┘ └─────┘ └─────┘      │
│                                         │
│  Current tool: Point                    │
│  Click on object to segment             │
│                                         │
│  Active segments: 3                     │
│  [🗑 Clear all] [↩ Undo]               │
└─────────────────────────────────────────┘
```

#### Инструменты

| Инструмент | Иконка | Описание | Горячая клавиша |
|------------|--------|----------|-----------------|
| **Point** | 👆 | Кликните на объект | `1` |
| **Rectangle** | ▭ | Прямоугольник вокруг объекта | `2` |
| **Polygon** | ⬡ | Многосторонняя форма | `3` |
| **Freehand** | ✏ | Свободное рисование | `4` |

#### Point Tool

```
Point tool workflow:
┌─────────────────────────────────────────┐
│  1. Выберите Point tool                 │
│                                         │
│  2. Кликните на объект:                 │
│                                         │
│         ┌─────────┐                     │
│         │  🐜     │  ← click here       │
│         └─────────┘                     │
│                 ↓                       │
│         ┌─────────┐                     │
│         │█████████│  ← mask generated  │
│         └─────────┘                     │
│                                         │
│  3. Если неправильно — кликните        │
│     background point (Shift+click)      │
└─────────────────────────────────────────┘
```

#### Rectangle Tool

```
Rectangle tool workflow:
┌─────────────────────────────────────────┐
│  1. Выберите Rectangle tool             │
│                                         │
│  2. Перетащите вокруг объекта:          │
│                                         │
│     ┌───────────────┐                   │
│     │ ┌───────────┐ │                   │
│     │ │  🐜🐜🐜  │ │ ← drag here      │
│     │ └───────────┘ │                   │
│     └───────────────┘                   │
│                     ↓                   │
│     ┌───────────────┐                   │
│     │ █████████████ │                   │
│     │ █  🐜🐜🐜  █ │                   │
│     │ █████████████ │                   │
│     └───────────────┘                   │
└─────────────────────────────────────────┘
```

#### Polygon Tool

```
Polygon tool workflow:
┌─────────────────────────────────────────┐
│  1. Выберите Polygon tool               │
│                                         │
│  2. Кликайте по контуру объекта:        │
│                                         │
│        • — click points                 │
│       / \                               │
│      •   •                              │
│      |   |                              │
│      \\ /                               │
│       •                                 │
│                                         │
│  3. Double-click или замыкание:         │
│                                         │
│     ┌─────────────┐                     │
│     │ ███████████ │                     │
│     │ ██🐜🐜██  │                     │
│     │ ███████████ │                     │
│     └─────────────┘                     │
└─────────────────────────────────────────┘
```

#### Freehand Tool

```
Freehand tool workflow:
┌─────────────────────────────────────────┐
│  1. Выберите Freehand tool              │
│                                         │
│  2. Рисуйте вокруг объекта:             │
│                                         │
│     ~~~~~~~~                            │
│   ~~      ~~                            │
│  ~    🐜   ← draw around                │
│   ~~      ~~                            │
│     ~~~~~~~~                            │
│                 ↓                       │
│     ┌─────────────┐                     │
│     │ ███████████ │                     │
│     │ ██🐜🐜██  │                     │
│     │ ███████████ │                     │
│     └─────────────┘                     │
└─────────────────────────────────────────┘
```

### Propagate Mode

Автоматическое распространение сегментации на все кадры видео.

```
Propagation Settings:
┌─────────────────────────────────────────┐
│  Mode: [Propagate ▼]                   │
│                                         │
│  Source frame: [00:05:00]              │
│                                         │
│  Settings:                              │
│  ┌───────────────────────────────────┐  │
│  │ Speed: [Fast] [Balanced] [Best]  │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Smoothing: [On] [Off]                 │
│  Temporal consistency: [On]            │
│                                         │
│  Frame range:                           │
│  From: [00:00:00] To: [00:15:00]       │
│  All frames: [✓]                       │
│                                         │
│  [▶ Start Propagation]                 │
└─────────────────────────────────────────┘
```

#### Speed modes

| Mode | Качество | Скорость | Использование |
|------|----------|----------|---------------|
| **Fast** | Среднее | 100 FPS | Быстрый просмотр |
| **Balanced** | Высокое | 50 FPS | Полевая работа |
| **Best** | Максимальное | 20 FPS | Точный анализ |

#### Smoothing

```
Temporal smoothing:
┌─────────────────────────────────────────┐
│  Without smoothing:                     │
│  Frame 1: [██████]                      │
│  Frame 2: [█████ ] ← jitter             │
│  Frame 3: [██████]                      │
│                                         │
│  With smoothing:                        │
│  Frame 1: [██████]                      │
│  Frame 2: [██████] ← smooth             │
│  Frame 3: [██████]                      │
│                                         │
│  Smoothing strength: [50%]              │
└─────────────────────────────────────────┘
```

## Управление сегментами

### Панель сегментов

```
Segments Panel:
┌─────────────────────────────────────────┐
│  Active Segments: 4                     │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │ ☑ Segment 1 - Ant worker          │  │
│  │    Mask: [████████]               │  │
│  │    Area: 1,245 px (0.12 cm²)     │  │
│  │    [👁] [🗑] [✏ Rename]          │  │
│  ├───────────────────────────────────┤  │
│  │ ☑ Segment 2 - Cricket             │  │
│  │    Mask: [████████]               │  │
│  │    Area: 3,890 px (0.38 cm²)     │  │
│  │    [👁] [🗑] [✏ Rename]          │  │
│  ├───────────────────────────────────┤  │
│  │ ☐ Segment 3 - Beetle (hidden)    │  │
│  │    [👁 show] [🗑] [✏ Rename]     │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Actions:                               │
│  [🗑 Clear all] [↩ Undo] [👁 Show all] │
└─────────────────────────────────────────┘
```

### Действия с сегментами

| Действие | Описание | Горячая клавиша |
|----------|----------|-----------------|
| **Show/hide** | Переключить видимость | `H` |
| **Delete** | Удалить сегмент | `Del` |
| **Rename** | Переименовать | `R` |
| **Merge** | Объединить с другим | `Ctrl+M` |
| **Split** | Разделить на части | `Ctrl+Shift+S` |

## Визуализация масок

### Отображение на canvas

```
Mask visualization modes:
┌─────────────────────────────────────────┐
│  Mode: [Overlay ▼]                     │
│                                         │
│  • Overlay — полупрозрачная маска       │
│  • Outline — только контур             │
│  • Fill — заполненный                  │
│  • Isolate — только маска              │
│                                         │
│  Overlay opacity: [50%]                │
│  Outline width: [2] px                 │
│  Outline color: [Red]                  │
│                                         │
│  [👁 Toggle] [📊 Stats]                │
└─────────────────────────────────────────┘
```

### Статистика масок

```
Mask statistics:
┌─────────────────────────────────────────┐
│  Total segments: 4                      │
│                                         │
│  ┌────────────┬───────────┬──────────┐  │
│  │ Segment    │ Pixels    │ Area cm² │  │
│  ├────────────┼───────────┼──────────┤  │
│  │ Ant worker │ 1,245     │ 0.12     │  │
│  │ Cricket    │ 3,890     │ 0.38     │  │
│  │ Beetle     │ 2,156     │ 0.21     │  │
│  │ Larva      │ 456       │ 0.04     │  │
│  ├────────────┼───────────┼──────────┤  │
│  │ Total      │ 7,747     │ 0.75     │  │
│  └────────────┴───────────┴──────────┘  │
│                                         │
│  Scale: 1 cm = 1,650 px                │
│  Calibrated from: GPS + camera specs   │
└─────────────────────────────────────────┘
```

## Экспорт сегментов

### Форматы экспорта

| Формат | Расширение | Описание |
|--------|------------|----------|
| **PNG mask** | `.png` | Бинарная маска |
| **JSON** | `.json` | Метаданные + ссылки |
| **COCO** | `.json` | Стандарт COCO segmentation |
| **Polygon** | `.geojson` | Геоjson полигоны |

### Пример PNG mask

```
Original:          Mask:
┌──────┐          ┌──────┐
│🐜🐜🐜│          │██████│
│🐜 🐜 │    →     │██████│
│ 🐜🐜🐜│          │██████│
└──────┘          └──────┘
                   (white = object)
```

### Пример JSON

```json
{
  "image": "IMG_001.jpg",
  "segments": [
    {
      "id": 1,
      "label": "Ant worker",
      "mask_path": "masks/IMG_001_seg1.png",
      "area_pixels": 1245,
      "area_cm2": 0.12,
      "polygon": [[120,45], [180,45], [180,95], [120,95]]
    }
  ]
}
```

## API Reference

### Interactive segmentation

```bash
# Segment from point
curl -X POST http://localhost:8000/api/segment/interactive \
  -F "image=@IMG_001.jpg" \
  -F "tool=point" \
  -F "point_x=250" \
  -F "point_y=180"

# Response:
{
  "status": "success",
  "mask_url": "/data/masks/IMG_001_seg1.png",
  "polygon": [[250,180], [260,175], ...],
  "area_pixels": 1245
}
```

### Propagate segmentation

```bash
# Start propagation
curl -X POST http://localhost:8000/api/segment/propagate \
  -F "video=video_001.mp4" \
  -F "source_frame=300" \
  -F "speed=balanced" \
  -F "smoothing=true"

# Response:
{
  "status": "processing",
  "job_id": "prop_20260919_001",
  "total_frames": 27000,
  "estimated_time_seconds": 540
}

# Check progress
curl http://localhost:8000/api/segment/propagate/prop_20260919_001

# Response:
{
  "status": "processing",
  "progress": 45,
  "processed_frames": 12150,
  "total_frames": 27000
}
```

## Производительность

### FPS сегментации (RTX 4070)

| Режим | Разрешение | FPS | Время/кадр |
|-------|------------|-----|------------|
| **Interactive** | 1920×1080 | 30 FPS | 33 ms |
| **Interactive** | 3840×2160 | 12 FPS | 83 ms |
| **Propagate Fast** | 1920×1080 | 100 FPS | 10 ms |
| **Propagate Balanced** | 1920×1080 | 50 FPS | 20 ms |
| **Propagate Best** | 1920×1080 | 20 FPS | 50 ms |

### VRAM usage

```
SAM3 VRAM budget:
┌──────────────────────────────────────┐
│ Model weights:          1.5 GB       │
│ Feature cache:          500 MB       │
│ Per mask output:        10 MB        │
│ Propagate frame buffer: 300 MB       │
│                                      │
│ Total for 100 segments: ~2.5 GB     │
└──────────────────────────────────────┘
```

## Troubleshooting

### Проблема: Маска неточная

```
Inaccurate mask
Solution:
1. Используйте Polygon tool вместо Point
2. Добавьте more points on object
3. Добавьте background points (Shift+click)
4. Попробуйте другой tool
5. Увеличьте resolution изображения
```

### Проблема: Propagation нестабильна

```
Unstable propagation
Solution:
1. Включите smoothing
2. Измените speed mode на Balanced
3. Выберите лучше источник (clear frame)
4. Уменьшите range propagation
```

### Проблема: Мало объектов сегментировано

```
Missing segments
Solution:
1. Проверьте visibility (☑ checkbox)
2. Увеличьте opacity overlay
3. Попробуйте другой visualization mode
4. Проверьте zoom level
```

### Проблема: Медленная сегментация

```
Slow segmentation
Solution:
1. Используйте Propagate Fast вместо Interactive
2. Уменьшите resolution
3. Проверьте GPU: nvidia-smi
4. Закройте другие GPU-приложения
```

## Советы по эффективности

### Для точной сегментации

1. Используйте Polygon tool для сложных форм
2. Добавьте background points для уточнения
3. Propagate Best для критичных задач
4. Включите smoothing для видео

### Для быстрой обработки

1. Rectangle tool — быстрый старт
2. Propagate Fast для больших видео
3. Batch mask export
4. Автоматическая сегментация из detection

### Для анализа размеров

1. Калибруйте scale (GPS + camera specs)
2. Используйте area_cm2 вместо pixels
3. Propagate Balanced для баланса
4. Экспортируйте COCO для статистики

## Следующие шаги

1. **[Batch Scan](./BATCH_SCAN.md)** — пакетная обработка
2. **[Change Detection](./CHANGE_DETECTION.md)** — сравнение до/после
3. **[AI Analysis](./AI_ANALYSIS.md)** — Ollama интеграция
4. **[Troubleshooting](./TROUBLESHOOTING.md)** — устранение неполадок

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
