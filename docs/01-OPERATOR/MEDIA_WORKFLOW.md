# Media Workflow — MuraveiVision PRO

> **Загрузка, просмотр и управление медиафайлами в полевых условиях.**

## Обзор

Media Workflow — это система загрузки, просмотра и управления медиафайлами в MuraveiVision PRO. Поддерживаются изображения и видео с расширенными функциями просмотра, GPS-привязкой и пакетной загрузкой.

## Загрузка медиа

### 1. Drag & Drop

```
Панель Media:
┌─────────────────────────────────────────┐
│  📁 Load Media                          │
│  ┌───────────────────────────────────┐  │
│  │                                   │  │
│  │   Drag & drop files here          │  │
│  │   or click to browse              │  │
│  │                                   │  │
│  │   .mp4  .mov  .avi  .jpg  .png   │  │
│  │                                   │  │
│  └───────────────────────────────────┘  │
│                                         │
│  📂 Recent files:                       │
│  • session_001.mp4    2.3 GB  14:32    │
│  • field_camera_042.jpg  4.1 MB        │
│  • trap_video_07.mp4    890 MB  05:18  │
└─────────────────────────────────────────┘
```

**Действия:**
- Перетащите файл(ы) в область загрузки
- Или нажмите для выбора файла(ов)
- Поддерживается множественный выбор

### 2. Выбор файла

```
File dialog:
┌─────────────────────────────────────────┐
│  Open File                              │
│                                         │
│  📁 C:\data\field_session_01\           │
│  ┌───────────────────────────────────┐  │
│  │ Name              Size    Type    │  │
│  ├───────────────────────────────────┤  │
│  │ IMG_0001.jpg      4.2 MB  Image  │  │
│  │ IMG_0002.jpg      4.1 MB  Image  │  │
│  │ video_001.mp4     2.3 GB  Video  │  │
│  │ track_001.gpx     12 KB   GPS    │  │
│  └───────────────────────────────────┘  │
│                                         │
│  [Cancel]  [Open]                       │
└─────────────────────────────────────────┘
```

## Поддерживаемые форматы

### Изображения

| Формат | Расширение | Поддержка | Примечания |
|--------|------------|-----------|------------|
| JPEG | `.jpg`, `.jpeg` | ✅ | Прогрессивный JPEG не поддерживается |
| PNG | `.png` | ✅ | С прозрачностью и без |
| BMP | `.bmp` | ✅ | Без сжатия |
| TIFF | `.tiff`, `.tif` | ⚠️ | Только 8-bit |
| WebP | `.webp` | ⚠️ | Только базовый |

### Видео

| Формат | Расширение | Кодек | Поддержка |
|--------|------------|-------|-----------|
| MP4 | `.mp4` | H.264 | ✅ Полная |
| MP4 | `.mp4` | H.265 | ⚠️ Только CPU decode |
| MOV | `.mov` | H.264 | ✅ Полная |
| AVI | `.avi` | MJPEG | ✅ Полная |
| AVI | `.avi` | Xvid | ⚠️ Частичная |

> **Рекомендация:** Используйте MP4 с H.264 для максимальной совместимости.

## Видеоплеер

### Управление воспроизведением

```
Video Player Controls:
┌─────────────────────────────────────────┐
│                                         │
│            ┌─────────┐                  │
│            │  VIDEO  │                  │
│            │  FRAME  │                  │
│            └─────────┘                  │
│                                         │
│  ◁◁  ▷  ⏸  ▷▷  🔊  [====|====]  05:23 │
│                                         │
│  FPS: 30  |  Duration: 14:32            │
│  Resolution: 3840×2160  |  2.3 GB       │
└─────────────────────────────────────────┘
```

### Кнопки управления

| Кнопка | Действие | Горячая клавиша |
|--------|----------|-----------------|
| `◁◁` | Предыдущий кадр | `←` |
| `▷` | Следующий кадр | `→` |
| `▷` | Play | `Space` |
| `⏸` | Pause | `Space` |
| `▷▷` | Перемотка вперёд | `→` (удержание) |
| `🔊` | Mute/unmute | `M` |
| `[====|====]` | Progress slider | `←` `→` |

### Zoom и Pan

```
Zoom controls:
┌─────────────────────────────────────────┐
│  [+] Zoom In        [+] 150% [+]       │
│  [-] Zoom Out                            │
│  [R] Reset View                          │
│  [F] Fit to Screen                       │
│                                         │
│  Mouse:                                  │
│  • Scroll wheel — zoom                   │
│  • Middle mouse drag — pan               │
│  • Double-click — reset                  │
└─────────────────────────────────────────┘
```

## GPS Sidecar файлы

### Поддерживаемые GPS форматы

MuraveiVision PRO автоматически загружает GPS-данные из сопутствующих файлов:

| Формат | Расширение | Описание |
|--------|------------|----------|
| GPX | `.gpx` | GPS трек в формате GPX 1.1 |
| JSON | `.json` | EXIF метаданные с GPS |
| CSV | `.csv` | Простой CSV с координатами |

### Формат GPX

```xml
<!-- video.gpx -->
<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="MuraveiVision">
  <trk>
    <name>Field Session 01</name>
    <trkseg>
      <trkpt lat="55.7558" lon="37.6173">
        <time>2026-09-19T10:00:00Z</time>
      </trkpt>
      <trkpt lat="55.7559" lon="37.6174">
        <time>2026-09-19T10:00:05Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
```

### Формат JSON (EXIF)

```json
// video.json
{
  "ExifGPS": {
    "GPSLatitude": [55, 45, 20.88],
    "GPSLatitudeRef": "N",
    "GPSLongitude": [37, 37, 2.27],
    "GPSLongitudeRef": "E",
    "GPSDateStamp": "2026:09:19 10:00:00"
  }
}
```

### Привязка GPS к медиа

```
GPS mapping rules:
┌─────────────────────────────────────────┐
│  File naming (auto-match):              │
│  video.mp4  ←→  video.gpx               │
│  image.jpg  ←→  image.json              │
│                                         │
│  Timestamp matching:                    │
│  Video frames → GPX trackpoints         │
│  by closest timestamp                   │
│                                         │
│  Display:                               │
│  ☑ Show GPS coordinates                │
│  ☑ Show map overlay                    │
│  ☑ Show altitude                       │
└─────────────────────────────────────────┘
```

## Библиотека медиа

### Recent Files

```
Media Library:
┌─────────────────────────────────────────┐
│  🔍 Search files...                    │
│                                         │
│  Filters:                               │
│  [All] [Images] [Video] [GPS]          │
│                                         │
│  Sort: [Date ▼] [Name ▼] [Size ▼]     │
│                                         │
│  ┌──────────┐ ┌──────────┐             │
│  │ IMG_0001 │ │ IMG_0002 │             │
│  │ 4.2 MB   │ │ 4.1 MB   │             │
│  │ 📍55.75N │ │ 📍55.76N │             │
│  └──────────┘ └──────────┘             │
│                                         │
│  ┌──────────┐ ┌──────────┐             │
│  │ video_01 │ │ video_02 │             │
│  │ 2.3 GB   │ │ 1.8 GB   │             │
│  │ 🎬14:32  │ │ 🎬11:05  │             │
│  └──────────┘ └──────────┘             │
│                                         │
│  Total: 156 files | 45.2 GB             │
└─────────────────────────────────────────┘
```

### Метаданные файла

```
File Properties:
┌─────────────────────────────────────────┐
│  IMG_0001.jpg                           │
│                                         │
│  General:                               │
│  • Type: JPEG Image                     │
│  • Size: 4.2 MB                         │
│  • Dimensions: 4032×3024                │
│  • Aspect ratio: 4:3                    │
│  • DPI: 72                              │
│                                         │
│  Video (if applicable):                 │
│  • Duration: 14:32                      │
│  • FPS: 30                              │
│  • Codec: H.264                         │
│  • Total frames: 25,920                 │
│                                         │
│  GPS:                                   │
│  • Latitude: 55.7558 N                  │
│  • Longitude: 37.6173 E                 │
│  • Altitude: 156 m                      │
│  • Source: video.gpx                    │
│                                         │
│  Timestamps:                            │
│  • Created: 2026-09-19 10:00:00        │
│  • Modified: 2026-09-19 10:00:00       │
│  • Session: field_session_01            │
└─────────────────────────────────────────┘
```

## Пакетная загрузка

### Загрузка папки

```
Batch Load:
┌─────────────────────────────────────────┐
│  📂 Load Folder                         │
│                                         │
│  Select folder:                         │
│  ┌───────────────────────────────────┐  │
│  │ C:\data\field_session_01\         │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Options:                               │
│  ☑ Include subfolders                   │
│  ☑ Auto-detect GPS sidecars            │
│  ☑ Generate thumbnails                 │
│  File types: [.mp4 .jpg .png .mov]    │
│                                         │
│  Preview:                               │
│  Found: 156 files (45.2 GB)             │
│  Images: 148 | Videos: 8               │
│                                         │
│  [Cancel]  [Load All]                   │
└─────────────────────────────────────────┘
```

### Генерация миниатюр

```
Thumbnail generation:
┌─────────────────────────────────────────┐
│  Progress: ███████████░░░░ 75%          │
│                                         │
│  Generating thumbnails...               │
│  File 117/156: IMG_0117.jpg             │
│                                         │
│  Settings:                              │
│  • Size: 200×150 px                     │
│  • Format: JPEG (quality 85)            │
│  • Storage: .thumbnails/ cache          │
│                                         │
│  [Pause] [Cancel]                       │
└─────────────────────────────────────────┘
```

## Экспорт медиа

### Конвертация форматов

```
Export options:
┌─────────────────────────────────────────┐
│  Format:  [MP4 ▼]                       │
│  • MP4 (H.264)                          │
│  • MP4 (H.265)                          │
│  • AVI (MJPEG)                          │
│  • GIF (animated)                       │
│  • PNG sequence                         │
│  • JPEG sequence                        │
│                                         │
│  Quality: [High ████████░░ 80%]        │
│  Resolution: [Original] [1080p] [720p] │
│  FPS: [Original] [30] [15] [5]         │
│                                         │
│  Crop: [X:0 Y:0 W:1920 H:1080]         │
│  Rotation: [0°] [90°] [180°] [270°]   │
│                                         │
│  [Export]                               │
└─────────────────────────────────────────┘
```

### Экспорт кадров

```
Frame extraction:
┌─────────────────────────────────────────┐
│  Source: video_001.mp4                  │
│                                         │
│  Mode: [Extract all] [Range] [Interval]│
│                                         │
│  If Range:                              │
│  From: 00:05:00  To: 00:10:00          │
│                                         │
│  If Interval:                           │
│  Every: [1] second(s)                   │
│                                         │
│  Output format: [JPEG] [PNG]           │
│  Quality: [90%]                         │
│                                         │
│  Output folder: C:\data\extracted\      │
│  Estimated: 27,000 files (108 GB)      │
│                                         │
│  [Extract]                              │
└─────────────────────────────────────────┘
```

## Советы по эффективности

### Оптимизация загрузки

1. **Используйте MP4/H.264** — максимальная совместимость и производительность
2. **Группируйте файлы по сессиям** — упрощает навигацию
3. **Включайте GPS sidecars** — автоматическая привязка по имени файла
4. **Генерируйте thumbnails** — ускоряет просмотр библиотеки

### Оптимизация просмотра

1. **Zoom scroll wheel** — быстрый zoom на деталях
2. **Frame-by-frame ← →** — детальный анализ
3. **Progress slider** — быстрый переход к нужному месту
4. **Keyboard shortcuts** — максимальная скорость

### Оптимизация пакетной обработки

1. **Load folder** вместо файлов — загрузка всей папки
2. **Include subfolders** — рекурсивный поиск
3. **Auto-detect GPS** — автоматическая привязка
4. **Batch export** — конвертация нескольких файлов

## Troubleshooting

### Проблема: Видео не воспроизводится

```
Error: Unsupported codec
Solution:
1. Проверьте кодек (должен быть H.264 для MP4)
2. Конвертируйте в MP4/H.264 через export
3. Извлеките кадры как изображения
```

### Проблема: GPS не отображается

```
Error: GPS data not found
Solution:
1. Проверьте наличие .gpx или .json файла
2. Проверьте имя файла (должно совпадать)
3. Проверьте формат GPX (должен быть GPX 1.1)
4. Проверьте timestamps (должны совпадать)
```

### Проблема: Медленная загрузка больших файлов

```
Slow loading for 4K video
Solution:
1. Уменьшите resolution в export (1080p вместо 4K)
2. Извлеките кадры и работайте с изображениями
3. Увеличьте RAM (минимум 16 GB для 4K)
4. Используйте SSD для хранения
```

## Следующие шаги

1. **[Detection](./DETECTION.md)** — обнаружение объектов
2. **[Segmentation](./SEGMENTATION.md)** — сегментация SAM3
3. **[Batch Scan](./BATCH_SCAN.md)** — пакетная обработка
4. **[Troubleshooting](./TROUBLESHOOTING.md)** — устранение неполадок

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
