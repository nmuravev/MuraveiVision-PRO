# Быстрый старт — Оператор

> **Цель:** Загрузить медиа, запустить обнаружение, просмотреть результаты — за 5 минут.

## Предварительные требования

- Приложение развёрнуто и запущено
- Браузер открыт на `http://localhost:8000`
- GPU обнаружен (проверено диагностикой)

## Шаг 1: Загрузка медиа

### 1.1 Переход к панели Media

1. Откройте главное меню (☰)
2. Выберите **Media** в разделе Operator

### 1.2 Загрузка файла

```
Панель Media:
┌─────────────────────────────────────┐
│ 📁 Load Media                       │
│ ┌─────────────────────────────────┐ │
│ │ Drag & drop or click to upload  │ │
│ │                                 │ │
│ │   .mp4  .mov  .jpg  .png        │ │
│ └─────────────────────────────────┘ │
│                                     │
│ 📂 Recent files:                    │
│ • session_20260919_001.mp4  [2.3 GB]│
│ • field_camera_042.jpg     [4.1 MB] │
└─────────────────────────────────────┘
```

**Действия:**
- Перетащите файл в область загрузки
- Или нажмите для выбора файла
- Поддерживаемые форматы: `.mp4`, `.mov`, `.jpg`, `.png`, `.avi`

### 1.3 GPS sidecar (опционально)

Если есть GPS-данные в отдельном файле:

```
Файлы:
  video.mp4          ← основное медиа
  video.gpx          ← GPS трек (опционально)
  video.json         ← EXIF метаданные (опционально)
```

> **Формат GPX:** Требуется стандартный GPX 1.1 с `<trk>` сегментами.

## Шаг 2: Обнаружение объектов

### 2.1 Переход к панели Detection

```
Меню → Detection
```

### 2.2 Выбор модели

```
Панель Detection:
┌─────────────────────────────────────┐
│ Model Selection                      │
│ ┌─────────────────────────────────┐ │
│ │ YOLO26n-ft  ✓                   │ │
│ │ YOLO26s-ft                        │ │
│ │ YOLO26n-ft                        │ │
│ └─────────────────────────────────┘ │
│                                     │
│ SAHI Settings                       │
│ Slice height:  [512] px             │
│ Slice width:   [512] px             │
│ overlap:       [20] %               │
│ Threshold:     [0.50]               │
│ IoU:           [0.45]               │
│                                     │
│ [▶ Run Detection]                   │
└─────────────────────────────────────┘
```

**Параметры SAHI:**
- **Slice size:** 512×512 для больших изображений, 1024×1024 для HD
- **Overlap:** 20% для баланса точности и скорости
- **Threshold:** 0.50 по умолчанию, ниже = больше ложных срабатываний

### 2.3 Запуск обнаружения

1. Выберите модель
2. Настройте SAHI (опционально)
3. Нажмите **Run Detection**
4. Дождитесь завершения (индикатор прогресса)

```
Progress: ████████████░░░░ 75%
ETA: 12s
Processing slice 45/60...
```

### 2.4 Просмотр результатов

```
Canvas view:
┌─────────────────────────────────────┐
│                                     │
│   ┌───┐                             │
│   │🐜 │  Ant 0.95                   │
│   └───┘                             │
│         ┌──────┐                    │
│         │🦗   │  Cricket 0.87       │
│         └──────┘                    │
│                                     │
│  Objects: 2                         │
│  [👁 Show all] [📊 Stats] [💾 Export]│
└─────────────────────────────────────┘
```

**Управление отображением:**
- **Hover** на bounding box — показать класс и confidence
- **Click** на объект — выделить и показать детали
- **Show all** — переключить отображение всех объектов
- **Stats** — статистика по классам
- **Export** — экспорт результатов

## Шаг 3: Сегментация

### 3.1 Переход к панели Segmentation

```
Меню → Segmentation
```

### 3.2 Интерактивная сегментация (SAM3)

```
Панель Segmentation:
┌─────────────────────────────────────┐
│ Mode:  [Interactive ▼]              │
│                                       │
│ Tools:  [👆 Point] [▭ Rectangle]     │
│         [⬡ Polygon] [✏ Freehand]    │
│                                     │
│ [▶ Run Segmentation]                 │
└─────────────────────────────────────┘
```

**Инструменты:**
- **Point:** Кликните на объект для точечной маски
- **Rectangle:** Нарисуйте прямоугольник вокруг объекта
- **Polygon:** Многосторонняя форма для сложных объектов
- **Freehand:** Свободное рисование

### 3.3 Propagate режим

Для видео:

```
Propagation settings:
┌─────────────────────────────────────┐
│ Frames:  [All]                      │
│ Speed:   [Fast]                     │
│ Smoothing: [On]                     │
│                                     │
│ [▶ Propagate Segmentation]          │
└─────────────────────────────────────┘
```

> **Propagate:** Задайте маску на одном кадре — модель распространит на все кадры.

## Шаг 4: Пакетная обработка

### 4.1 Batch Scan

```
Панель Batch Scan:
┌─────────────────────────────────────┐
│ Scan Mode:  [Video by Detections]   │
│                                       │
│ Source:  [Select folder ▼]          │
│   📂 /data/field_session_01/         │
│   Files: 156 images                  │
│                                       │
│ Model:   [YOLO26n-ft]               │
│ SAHI:    [Auto]                      │
│                                       │
│ [▶ Start Batch Scan]                 │
└─────────────────────────────────────┘
```

### 4.2 Отслеживание прогресса

```
Batch Progress:
├── Total: 156 files
├── Completed: 89
├── Failed: 0
├── Progress: ██████████░░░░ 57%
├── ETA: 4m 23s
└── Current: IMG_4521.jpg
```

### 4.3 Результаты

```
Batch Results:
┌─────────────────────────────────────┐
│ Summary                             │
│ ├── Files processed: 156/156        │
│ ├── Total objects: 1,247            │
│ ├── Top class: Ant (67%)            │
│ ├── Avg confidence: 0.84            │
│ └── Failed: 0                       │
│                                     │
│ [📊 View Details] [💾 Export CSV]    │
└─────────────────────────────────────┘
```

## Шаг 5: Экспорт результатов

### 5.1 Форматы экспорта

```
Export options:
┌─────────────────────────────────────┐
│ Format:  [CSV ▼]                    │
│   • CSV — таблица объектов          │
│   • JSON — полный JSON              │
│   • YOLO — формат меток             │
│   • COCO — стандарт COCO            │
│                                     │
│ Include:                            │
│ ☑ Bounding boxes                    │
│ ☑ Masks                             │
│ ☑ Confidence scores                 │
│ ☑ GPS coordinates                  │
│ ☑ Timestamps                        │
│                                     │
│ [💾 Export]                          │
└─────────────────────────────────────┘
```

### 5.2 Пример CSV

```csv
file,class,confidence,x1,y1,x2,y2,mask_path,gps_lat,gps_lon
IMG_001.jpg,Ant,0.95,120,45,180,95,,55.7558,37.6173
IMG_001.jpg,Cricket,0.87,340,210,380,250,,55.7558,37.6173
IMG_002.jpg,Ant,0.91,55,30,115,85,,55.7559,37.6174
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

## Типичные сценарии

### Сценарий 1: Быстрый просмотр одного изображения

```
1. Load Media → загрузить изображение
2. Detection → выбрать YOLO26n-ft
3. Run Detection
4. Review results on canvas
5. Export (опционально)
```

### Сценарий 2: Пакетная обработка папки

```
1. Load Media → выбрать папку
2. Batch Scan → настроить параметры
3. Start Batch Scan
4. Monitor progress
5. Export results
```

### Сценарий 3: Детальный анализ с сегментацией

```
1. Load Media → загрузить изображение
2. Detection → запустить для обнаружения
3. Segmentation → выбрать Interactive mode
4. Draw mask on object of interest
5. Propagate (если видео)
6. Export masks
```

## Устранение неполадок

### Проблема: GPU не обнаружен

```
Error: CUDA not available
Solution:
1. Проверьте установку CUDA 12.x
2. Проверьте драйвер NVIDIA (551.86+)
3. Запустите diagnose.py
4. Попробуйте CPU mode (медленнее)
```

### Проблема: SAHI работает медленно

```
Slow SAHI performance
Solution:
1. Уменьшите slice size (512 вместо 1024)
2. Уменьшите overlap (10% вместо 20%)
3. Уменьшите batch size
4. Проверьте VRAM (должно быть >4 GB free)
```

### Проблема: Мало объектов обнаружено

```
Low detection count
Solution:
1. Уменьшите threshold (0.30 вместо 0.50)
2. Проверьте качество изображения
3. Попробуйте другую модель (YOLO26s вместо v8n)
4. Проверьте классы в модели
```

## Следующие шаги

1. **[Обнаружение](../01-OPERATOR/DETECTION.md)** — детально про detection
2. **[Сегментация](../01-OPERATOR/SEGMENTATION.md)** — SAM3 deep dive
3. **[Пакетная обработка](../01-OPERATOR/BATCH_SCAN.md)** — Batch Scan advanced
4. **[AI-анализ](../01-OPERATOR/AI_ANALYSIS.md)** — Ollama integration
5. **[3D-реконструкция](../01-OPERATOR/RECONSTRUCTION.md)** — COLMAP + DA3

## Поддержка

- **Документация:** [GLOSSARY.md](../GLOSSARY.md)
- **Устранение неполадок:** [Troubleshooting](../01-OPERATOR/TROUBLESHOOTING.md)
- **GitHub:** [Issues](https://github.com/nmuravev/MuraveiVision-PRO/issues)
