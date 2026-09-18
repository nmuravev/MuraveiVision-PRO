# Detection — MuraveiVision PRO

> **Обнаружение объектов с помощью YOLOv8/v11 и SAHI-слайсинга.**

## Обзор

Detection — это система обнаружения объектов в изображениях и видео с использованием моделей YOLO (You Only Look Once) v8 и v11 с поддержкой SAHI (Slicing Aided Hyper Inference) для больших изображений.

## Архитектура обнаружения

```
Detection Pipeline:
┌──────────────┐
│  Input Media │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐
│  Preprocessing│──→│  Resize/Normalize│
└──────┬───────┘     └──────┬───────┘
       │                    │
       ▼                    ▼
┌─────────────────────────────────┐
│     SAHI Slicing (if enabled)   │
│  ┌───┐ ┌───┐ ┌───┐             │
│  │ 1 │ │ 2 │ │ 3 │ ... N       │
│  └───┘ └───┘ └───┘             │
└──────┬──────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│     YOLO Model Inference        │
│  • YOLOv8n / v8s / v11n        │
│  • Batch processing             │
│  • GPU acceleration (CUDA)      │
└──────┬──────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│     NMS (Non-Max Suppression)   │
│  • IoU threshold filtering      │
│  • Confidence threshold         │
│  • Class filtering              │
└──────┬──────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│     Results                     │
│  • Bounding boxes               │
│  • Class labels                 │
│  • Confidence scores            │
│  • Masks (if seg model)         │
└─────────────────────────────────┘
```

## Модели YOLO

### Сравнение моделей

| Модель | Размер (MB) | Speed (FPS) | mAP50 | Точность | Использование |
|--------|-------------|-------------|-------|----------|---------------|
| **YOLOv8n** | 6.1 | 150 | 37.1 | Базовая | Быстрый просмотр, edge devices |
| **YOLOv8s** | 22.2 | 85 | 44.9 | Средняя | Полевая работа, баланс |
| **YOLOv8m** | 50.6 | 45 | 50.2 | Высокая | Детальный анализ |
| **YOLOv8l** | 86.7 | 30 | 52.9 | Очень высокая | Production |
| **YOLOv8x** | 134.1 | 20 | 53.9 | Максимальная | Точные измерения |
| **YOLOv11n** | 6.3 | 160 | 38.5 | Базовая | Новое поколение, fast |
| **YOLOv11s** | 21.5 | 90 | 46.0 | Средняя | Новое поколение, balanced |

> **Рекомендация:** YOLOv8s-ft для полевой работы, YOLOv8n-ft для скорости.

### Fine-tuned модели

```
Custom models (ft = fine-tuned):
┌─────────────────────────────────────────┐
│  Model: yolo8s-ant-v3.pt                │
│  • Trained on: ant_colony_dataset       │
│  • Classes: 5 (worker, queen, soldier...)│
│  • mAP50: 94.2%                         │
│  • Size: 22.4 MB                        │
│  • Location: backend/models/custom/     │
└─────────────────────────────────────────┘
```

## SAHI Slicing

### Что такое SAHI?

SAHI (Slicing Aided Hyper Inference) — техника разбиения больших изображений на меньшие tiles (слайсы) для более точного обнаружения мелких объектов.

```
SAHI Concept:
┌─────────────────────────────────────────┐
│  Original image (8192×6144)             │
│  ┌───────────────────────────────────┐  │
│  │                                   │  │
│  │    ┌────┐ ┌────┐                 │  │
│  │    │ S1 │ │ S2 │  Small objects  │  │
│  │    └────┘ └────┘  missed!        │  │
│  │                                   │  │
│  └───────────────────────────────────┘  │
│                    ↓                    │
│  Sliced into 512×512 tiles:             │
│  ┌───┐───┐───┐     ┌───┐              │
│  │ S1│ S2│ S3│  ...│ Sn│               │
│  └───┘───┘───┘     └───┘              │
│    ↓    ↓    ↓         ↓               │
│  ┌────┐┌────┐┌────┐   ┌────┐          │
│  │Ant ││Ant ││Cricket│ │Ant │          │
│  └────┘└────┘└─────┘   └────┘          │
│                    ↓                    │
│  Merged results (NMS):                 │
│  ┌────┐      ┌────┐                    │
│  │Ant ││Cricket││Ant │                 │
│  └────┘      └────┘                    │
└─────────────────────────────────────────┘
```

### Параметры SAHI

| Параметр | Диапазон | По умолчанию | Описание |
|----------|----------|--------------|----------|
| **Slice height** | 256-2048 | 512 | Высота слайса в пикселях |
| **Slice width** | 256-2048 | 512 | Ширина слайса в пикселях |
| **Overlap %** | 0-50 | 20 | Перекрытие между слайсами |
| **Threshold** | 0.1-0.9 | 0.5 | Минимальный confidence |
| **IoU** | 0.1-0.9 | 0.45 | NMS IoU threshold |

### Рекомендации по настройке SAHI

| Сценарий | Slice size | Overlap | Threshold | IoU |
|----------|------------|---------|-----------|-----|
| **Большие объекты** | 1024×1024 | 10% | 0.50 | 0.45 |
| **Мелкие объекты** | 512×512 | 20% | 0.35 | 0.40 |
| **Очень мелкие** | 256×256 | 30% | 0.25 | 0.35 |
| **Быстрый просмотр** | 1024×1024 | 10% | 0.50 | 0.50 |
| **Макс. точность** | 512×512 | 30% | 0.30 | 0.40 |

## Панель Detection

```
Detection Panel:
┌─────────────────────────────────────────────┐
│  Model Selection                             │
│  ┌───────────────────────────────────────┐  │
│  │ YOLOv8s-ft  ✓                         │  │
│  │ YOLOv8n-ft                            │  │
│  │ YOLOv11s                              │  │
│  │ yolo8s-ant-v3 (custom)                │  │
│  └───────────────────────────────────────┘  │
│                                             │
│  SAHI Settings                              │
│  ┌─────────────┐  ┌─────────────┐          │
│  │ Height: [512]│  │ Width: [512]│          │
│  └─────────────┘  └─────────────┘          │
│  Overlap: [20]%  Threshold: [0.50]         │
│  IoU: [0.45]                               │
│                                             │
│  Class Filter                               │
│  ☑ Ant  ☑ Cricket  ☑ Beetle                │
│  ☑ Spider   ☑ Larva                         │
│                                             │
│  Options                                    │
│  ☑ Enable SAHI                             │
│  ☑ Show confidence                         │
│  ☑ Show class labels                       │
│  ☑ HUD exclusion (auto-blur)              │
│                                             │
│  [▶ Run Detection]  [⏹ Cancel]             │
└─────────────────────────────────────────────┘
```

## Визуализация результатов

### Bounding boxes

```
Canvas with detections:
┌─────────────────────────────────────────┐
│                                         │
│     ┌─────────────┐                     │
│     │  🐜 Ant     │ 0.95                │
│     │  0.95       │                     │
│     └─────────────┘                     │
│                                         │
│              ┌──────────┐               │
│              │🦗 Cricket│ 0.87          │
│              │ 0.87     │               │
│              └──────────┘               │
│                                         │
│  Legend:                                │
│  🐜 Ant (2)  🦗 Cricket (1)             │
│  Colors by class                        │
└─────────────────────────────────────────┘
```

### Цвета по классам

| Класс | Цвет | Hex |
|-------|------|-----|
| Ant | 🔴 Red | #FF0000 |
| Cricket | 🔵 Blue | #0000FF |
| Beetle | 🟢 Green | #00FF00 |
| Spider | 🟡 Yellow | #FFFF00 |
| Larva | 🟣 Purple | #800080 |

> **Цвета настраиваются** в `config/class_colors.yaml`.

## HUD Exclusion

### Auto-blur объектов

```
HUD Exclusion:
┌─────────────────────────────────────────┐
│  When detection overlaps with HUD:      │
│                                         │
│  ☑ Enable HUD exclusion                │
│  Blur radius: [5] px                    │
│  Opacity: [80]%                         │
│                                         │
│  HUD zones:                            │
│  ┌───────────────────────────────────┐  │
│  │ HUD TOP (info bar)                │  │
│  │                                   │  │
│  │           ┌───┐                   │  │
│  │           │🐜 │ ← blurred!        │  │
│  │           └───┘                   │  │
│  │                                   │  │
│  │ HUD BOTTOM (controls)             │  │
│  └───────────────────────────────────┘  │
│                                         │
│  [Apply] [Reset]                        │
└─────────────────────────────────────────┘
```

## Экспорт результатов

### Форматы экспорта

| Формат | Расширение | Описание | Использование |
|--------|------------|----------|---------------|
| **CSV** | `.csv` | Таблица объектов | Excel, анализ |
| **JSON** | `.json` | Полный JSON | API, интеграции |
| **YOLO** | `.txt` | Формат меток YOLO | Переобучение |
| **COCO** | `.json` | Стандарт COCO | Публикация |

### Пример CSV

```csv
file,class,confidence,x1,y1,x2,y2
IMG_001.jpg,Ant,0.95,120,45,180,95
IMG_001.jpg,Cricket,0.87,340,210,380,250
IMG_002.jpg,Ant,0.91,55,30,115,85
```

### Пример YOLO format

```
# IMG_001.txt
0 0.345 0.234 0.050 0.083
1 0.678 0.567 0.040 0.060

# Format: class_id x_center y_center width height (normalized)
```

### Пример COCO

```json
{
  "info": {
    "description": "MuraveiVision detection",
    "version": "3.2.0"
  },
  "images": [
    {
      "id": 1,
      "file": "IMG_001.jpg",
      "width": 4032,
      "height": 3024
    }
  ],
  "annotations": [
    {
      "id": 1,
      "image_id": 1,
      "category_id": 0,
      "bbox": [120, 45, 60, 50],
      "score": 0.95
    }
  ],
  "categories": [
    {"id": 0, "name": "Ant"},
    {"id": 1, "name": "Cricket"}
  ]
}
```

## API Reference

### Запуск обнаружения

```bash
# Single image detection
curl -X POST http://localhost:8000/api/detect \
  -F "image=@IMG_001.jpg" \
  -F "model=yolo8s-ft" \
  -F "sahi_enabled=true" \
  -F "slice_height=512" \
  -F "slice_width=512" \
  -F "overlap=0.2" \
  -F "threshold=0.5" \
  -F "iou=0.45"

# Response:
{
  "status": "success",
  "detections": [
    {
      "class": "Ant",
      "confidence": 0.95,
      "bbox": [120, 45, 180, 95]
    }
  ],
  "processing_time_ms": 245
}
```

### Batch detection

```bash
# Folder detection
curl -X POST http://localhost:8000/api/detect/batch \
  -F "folder=@/data/field_session_01/" \
  -F "model=yolo8s-ft" \
  -F "recursive=true"

# Response:
{
  "status": "success",
  "total_files": 156,
  "processed": 156,
  "failed": 0,
  "total_detections": 1247,
  "processing_time_ms": 45230
}
```

## Производительность

### FPS по моделям (RTX 4070)

| Модель | 1920×1080 | 3840×2160 | 8192×6144 + SAHI |
|--------|-----------|-----------|-------------------|
| YOLOv8n | 180 FPS | 95 FPS | 12 FPS (64 tiles) |
| YOLOv8s | 95 FPS | 50 FPS | 6 FPS (64 tiles) |
| YOLOv8m | 48 FPS | 25 FPS | 3 FPS (64 tiles) |
| YOLOv8l | 32 FPS | 16 FPS | 2 FPS (64 tiles) |

### Оптимизация производительности

1. **Используйте FP16** — ускоряет в 2x на NVIDIA GPU
2. **Увеличьте batch size** — до 8 для лучшей throughput
3. **SAHI slice 512** — оптимальный баланс скорость/точность
4. **NMS on GPU** — быстрее CPU NMS в 5x

## Troubleshooting

### Проблема: Мало обнаружено объектов

```
Low detection count
Solution:
1. Уменьшите threshold (0.30 вместо 0.50)
2. Увеличьте SAHI overlap (30% вместо 20%)
3. Уменьшите slice size (256 вместо 512)
4. Проверьте классы в модели
5. Попробуйте другую модель (v8s вместо v8n)
```

### Проблема: Много ложных срабатываний

```
High false positive rate
Solution:
1. Увеличьте threshold (0.60 вместо 0.50)
2. Увеличьте IoU (0.50 вместо 0.45)
3. Используйте fine-tuned модель
4. Отфильтруйте классы
```

### Проблема: Медленная работа

```
Slow detection
Solution:
1. Проверьте GPU: nvidia-smi
2. Уменьшите SAHI slice size
3. Уменьшите overlap
4. Уменьшите batch size если OOM
5. Используйте YOLOv8n вместо v8s
```

### Проблема: CUDA out of memory

```
CUDA out of memory
Solution:
1. Уменьшите batch_size в config
2. Закройте другие GPU-приложения
3. Перезапустите backend
4. Используйте YOLOv8n (меньше модель)
```

## Советы по эффективности

### Для быстрых сессий

1. YOLOv8n-ft + SAHI off — максимальная скорость
2. Threshold 0.50, IoU 0.45 — по умолчанию
3. Batch detection для папок

### Для максимальной точности

1. YOLOv8s-ft или fine-tuned модель
2. SAHI 512×512, overlap 30%
3. Threshold 0.30, IoU 0.40
4. Manual review результатов

### Для полевых условий

1. YOLOv8s-ft — баланс скорость/точность
2. SAHI 512×512, overlap 20%
3. Threshold 0.45 — умеренный
4. Batch export в CSV

## Следующие шаги

1. **[Segmentation](./SEGMENTATION.md)** — SAM3 сегментация
2. **[Batch Scan](./BATCH_SCAN.md)** — пакетная обработка
3. **[AI Analysis](./AI_ANALYSIS.md)** — Ollama интеграция
4. **[Troubleshooting](./TROUBLESHOOTING.md)** — устранение неполадок

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
