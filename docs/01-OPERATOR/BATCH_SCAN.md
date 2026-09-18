# Batch Scan — MuraveiVision PRO

> **Пакетная обработка изображений и видео с обнаружением объектов.**

## Обзор

Batch Scan — система пакетной обработки множества файлов с автоматическим обнаружением объектов, сегментацией и экспортом результатов.

## Режимы Batch Scan

### 1. Video by Detections

```
Batch Scan — Video by Detections:
┌─────────────────────────────────────────┐
│  Scan Mode: [Video by Detections ▼]    │
│                                         │
│  Source:                                │
│  ┌───────────────────────────────────┐  │
│  │ 📂 /data/field_session_01/        │  │
│  └───────────────────────────────────┘  │
│  Files: 156 images (45.2 GB)           │
│                                         │
│  Model: [YOLOv8s-ft ▼]                 │
│                                         │
│  SAHI: [Auto] [Off] [Custom]          │
│  ┌─────────────┐  ┌─────────────┐     │
│  │ Height: [512]│  │ Width: [512]│     │
│  └─────────────┘  └─────────────┘     │
│  Overlap: [20]%  Threshold: [0.50]    │
│                                         │
│  Output:                                │
│  ☑ Save detections                    │
│  ☑ Save masks                          │
│  ☑ Export CSV                           │
│  Destination: /data/results/            │
│                                         │
│  [▶ Start Batch Scan] [⏹ Cancel]      │
└─────────────────────────────────────────┘
```

### 2. Folder Scan

```
Batch Scan — Folder Scan:
┌─────────────────────────────────────────┐
│  Scan Mode: [Folder Scan ▼]            │
│                                         │
│  Source folder:                         │
│  📂 /data/trap_cameras/                │
│  Subfolders: 12                         │
│  Total files: 2,340                    │
│                                         │
│  File filters:                          │
│  ☑ Images (.jpg .png)                  │
│  ☑ Videos (.mp4 .mov)                  │
│  ☑ Include subfolders                  │
│                                         │
│  Process:                               │
│  1. Detect objects                     │
│  2. Segment if needed                  │
│  3. Export results                     │
│                                         │
│  [▶ Start Scan]                        │
└─────────────────────────────────────────┘
```

### 3. Change Detection

```
Batch Scan — Change Detection:
┌─────────────────────────────────────────┐
│  Scan Mode: [Change Detection ▼]       │
│                                         │
│  Before:                                │
│  📂 /data/before_fire/                 │
│  Files: 89                              │
│                                         │
│  After:                                 │
│  📂 /data/after_fire/                  │
│  Files: 92                              │
│                                         │
│  Matching: [By name] [By GPS] [Manual] │
│  Threshold: [70]% similarity           │
│                                         │
│  [▶ Compare]                            │
└─────────────────────────────────────────┘
```

## Прогресс обработки

### Real-time progress

```
Batch Progress:
┌─────────────────────────────────────────┐
│  ████████████████████████░░░░ 78%       │
│                                         │
│  Files: 122/156                         │
│  Objects: 987                           │
│  Failed: 0                              │
│                                         │
│  ETA: 3m 42s                            │
│  Speed: 4.2 files/sec                   │
│                                         │
│  Current: IMG_0123.jpg                  │
│  Detections: 8                          │
│                                         │
│  [⏸ Pause] [📊 Details] [❌ Cancel]    │
└─────────────────────────────────────────┘
```

### Detailed log

```
Processing Log:
┌─────────────────────────────────────────┐
│  [10:23:45] Started batch scan          │
│  [10:23:46] IMG_0001.jpg - 4 objects   │
│  [10:23:47] IMG_0002.jpg - 2 objects   │
│  [10:23:48] IMG_0003.jpg - 7 objects   │
│  ...                                     │
│  [10:25:12] IMG_0122.jpg - 5 objects   │
│  [10:25:13] IMG_0123.jpg - 8 objects   │
│                                         │
│  Errors:                                │
│  (none)                                 │
│                                         │
│  [📄 Export log]                        │
└─────────────────────────────────────────┘
```

## Настройки обработки

### Advanced options

```
Advanced Settings:
┌─────────────────────────────────────────┐
│  Processing:                            │
│  • Batch size: [4]                      │
│  • GPU device: [0]                     │
│  • FP16: [✓]                           │
│  • SAHI: [✓]                           │
│                                         │
│  Filtering:                             │
│  • Min confidence: [0.30]              │
│  • Min area: [100] px                   │
│  • Classes: [All]                       │
│                                         │
│  Output:                                │
│  • Format: [CSV + JSON]                │
│  • Masks: [✓]                           │
│  • Bounding boxes: [✓]                  │
│  • GPS data: [✓]                        │
│                                         │
│  Error handling:                        │
│  • On error: [Skip] [Stop] [Retry]    │
│  • Max retries: [3]                     │
│                                         │
│  [Apply] [Reset]                        │
└─────────────────────────────────────────┘
```

### Batch size optimization

| Batch size | VRAM usage | Speed | Рекомендация |
|------------|------------|-------|--------------|
| 1 | 1.5 GB | 1x | Low VRAM GPU |
| 2 | 2.0 GB | 1.8x | 4 GB VRAM |
| 4 | 3.0 GB | 3x | 8 GB VRAM (recommended) |
| 8 | 5.0 GB | 5x | 12+ GB VRAM |
| 16 | 9.0 GB | 7x | 24 GB VRAM |

## Результаты batch scan

### Summary report

```
Batch Results Summary:
┌─────────────────────────────────────────┐
│  Scan completed: 2026-09-19 10:30:00   │
│                                         │
│  Files processed: 156/156               │
│  Failed: 0                              │
│  Total time: 6m 15s                     │
│  Avg speed: 4.2 files/sec               │
│                                         │
│  Detections:                            │
│  • Total objects: 1,247                 │
│  • Avg per file: 7.99                   │
│  • Top class: Ant (67%)                │
│  • Avg confidence: 0.84                │
│                                         │
│  Classes:                               │
│  ┌────────────┬───────────┬──────────┐  │
│  │ Class      │ Count     │ Avg Conf │  │
│  ├────────────┼───────────┼──────────┤  │
│  │ Ant        │ 835       │ 0.91     │  │
│  │ Cricket    │ 249       │ 0.87     │  │
│  │ Beetle     │ 100       │ 0.85     │  │
│  │ Spider     │ 42        │ 0.82     │  │
│  │ Larva      │ 21        │ 0.79     │  │
│  └────────────┴───────────┴──────────┘  │
│                                         │
│  [📊 View Details] [💾 Export]         │
└─────────────────────────────────────────┘
```

### Per-file results

```
Per-file breakdown:
┌─────────────────────────────────────────┐
│  File              │ Objects │ Time     │
│  ├─────────────────────────────────────┤  │
│  │ IMG_0001.jpg   │ 5       │ 0.45s   │  │
│  │ IMG_0002.jpg   │ 3       │ 0.42s   │  │
│  │ IMG_0003.jpg   │ 12      │ 1.23s   │  │
│  │ ...                                   │
│  │ IMG_0156.jpg   │ 7       │ 0.67s   │  │
│  ├─────────────────────────────────────┤  │
│  │ Total          │ 1,247   │ 6m 15s  │  │
│  └─────────────────────────────────────┘  │
│                                         │
│  Sort: [Time] [Objects] [Name]         │
│  Filter: [All] [High] [Low] [None]    │
└─────────────────────────────────────────┘
```

## Экспорт результатов

### Форматы экспорта

```
Export options:
┌─────────────────────────────────────────┐
│  Format:                                │
│  ☑ CSV (detections table)              │
│  ☑ JSON (full metadata)                │
│  ☑ YOLO (annotation format)            │
│  ☑ COCO (standard format)              │
│                                         │
│  Include:                               │
│  ☑ Bounding boxes                       │
│  ☑ Masks (PNG)                          │
│  ☑ Confidence scores                    │
│  ☑ GPS coordinates                     │
│  ☑ Timestamps                           │
│  ☑ Processing metadata                  │
│                                         │
│  Destination: /data/export/            │
│  Estimated size: 2.3 GB                 │
│                                         │
│  [💾 Export]                            │
└─────────────────────────────────────────┘
```

### Пример CSV экспорта

```csv
file,class,confidence,x1,y1,x2,y2,mask_path,gps_lat,gps_lon,processing_time
IMG_0001.jpg,Ant,0.95,120,45,180,95,masks/IMG_0001_seg1.png,55.7558,37.6173,0.45
IMG_0001.jpg,Cricket,0.87,340,210,380,250,masks/IMG_0001_seg2.png,55.7558,37.6173,0.45
IMG_0002.jpg,Ant,0.91,55,30,115,85,masks/IMG_0002_seg1.png,55.7559,37.6174,0.42
```

## Scheduled scans

### Автоматическая обработка

```
Scheduled Batch Scan:
┌─────────────────────────────────────────┐
│  Schedule:                              │
│  ☑ Enable scheduled scans              │
│                                         │
│  Frequency: [Every hour] [Daily]       │
│  Time: [02:00]                          │
│                                         │
│  Watch folder:                          │
│  📂 /data/incoming/                    │
│                                         │
│  On new files:                          │
│  1. Auto-detect objects                │
│  2. Save results                       │
│  3. Send notification                  │
│                                         │
│  Notifications:                         │
│  ☑ Email                                │
│  ☑ Local log                            │
│                                         │
│  [Save schedule]                        │
└─────────────────────────────────────────┘
```

## Troubleshooting

### Проблема: Ошибки обработки

```
Processing errors
Solution:
1. Проверьте log для деталей
2. Проверьте формат файла (поддерживаемые форматы)
3. Проверьте размер файла (макс 2 GB)
4. Попробуйте skip вместо stop
5. Увеличьте max retries
```

### Проблема: Медленная обработка

```
Slow batch processing
Solution:
1. Увеличьте batch size (если есть VRAM)
2. Используйте FP16
3. Уменьшите SAHI slice size
4. Отключите masks если не нужны
5. Проверьте GPU: nvidia-smi
```

### Проблема: Не все файлы обработаны

```
Incomplete processing
Solution:
1. Проверьте disk space
2. Проверьте error log
3. Увеличьте timeout
4. Попробуйте smaller batch
5. Проверьте permissions
```

## Советы по эффективности

### Для больших папок

1. Используйте Folder Scan с subfolders
2. Batch size 4-8 для 8+ GB VRAM
3. FP16 для ускорения
4. Scheduled scan для постоянной обработки

### Для точных результатов

1. SAHI 512×512, overlap 30%
2. Threshold 0.30
3. Include masks в output
4. Manual review low confidence

### Для быстрого анализа

1. SAHI off для небольших изображений
2. Batch size 16 для максимальной скорости
3. CSV only export (без masks)
4. Threshold 0.50 для фильтрации

## Следующие шаги

1. **[Change Detection](./CHANGE_DETECTION.md)** — сравнение до/после
2. **[AI Analysis](./AI_ANALYSIS.md)** — семантический анализ
3. **[Training](./TRAINING.md)** — fine-tuning моделей
4. **[Troubleshooting](./TROUBLESHOOTING.md)** — устранение неполадок

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
