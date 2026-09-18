# Возможности — MuraveiVision PRO

> **Полный обзор возможностей системы: обнаружение, сегментация, 3D, batch, network, AI.**

## Обзор возможностей

MuraveiVision PRO — комплексная система анализа видеоданных с расширенными возможностями для полевой работы.

## Таблица возможностей

| Возможность | Описание | Версия | Docs |
|-------------|----------|--------|------|
| **Detection** | YOLOv8/v11 + SAHI | v3.0+ | [Detection](./DETECTION.md) |
| **Segmentation** | SAM3 interactive & propagate | v3.1+ | [Segmentation](./SEGMENTATION.md) |
| **3D Reconstruction** | COLMAP, DA3, GSplat, Flight3D | v3.2+ | [Recon 3D](./RECON_3D.md) |
| **Batch Operations** | Batch Scan, Segmentation, Change | v3.0+ | [Batch](./BATCH_OPERATIONS.md) |
| **Network v3.3** | Hub+client, JWT, WebSocket | v3.3+ | [Network](./NETWORK.md) |
| **AI Analyst** | Ollama integration, rules, alerts | v3.1+ | [AI Analyst](./AI_ANALYST.md) |
| **Portable** | Standalone distribution | v3.0+ | [Portable](./PORTABLE.md) |

## Detection (YOLO/SAHI)

### Возможности

- YOLOv8n/s/m/l/x и YOLOv11n/s
- SAHI slicing для больших изображений
- Real-time detection
- Batch detection
- Class filtering
- Confidence thresholds
- HUD exclusion (auto-blur)
- Export: CSV, JSON, YOLO, COCO

### Производительность (RTX 4070)

| Модель | 1080p | 4K | 4K + SAHI |
|--------|-------|-----|-----------|
| YOLOv8n | 180 FPS | 95 FPS | 12 FPS |
| YOLOv8s | 95 FPS | 50 FPS | 6 FPS |

## Segmentation (SAM3)

### Возможности

- Interactive mode (point, rectangle, polygon, freehand)
- Propagate mode для видео
- Temporal smoothing
- Area calculation (pixels, cm²)
- Mask export (PNG, JSON, COCO)
- Multi-segment management

### Производительность (RTX 4070)

| Режим | FPS |
|-------|-----|
| Interactive | 30 FPS |
| Propagate Fast | 100 FPS |
| Propagate Balanced | 50 FPS |

## 3D Reconstruction (DA3)

### Возможности

- **DA3 Dense Backend** — Depth Anything 3 (NEW v3.2.0)
- COLMAP structure from motion
- GSplat Gaussian splatting
- Flight3D для aerial
- Point cloud visualization
- Mesh generation
- Export: OBJ, PLY, GLB

### VRAM requirements

| Модель | VRAM |
|--------|------|
| DA3-S | 2.1 GB |
| DA3-B | 4.3 GB |
| COLMAP | 4-8 GB |
| GSplat | 6-12 GB |

## Batch Operations

### Возможности

- **Batch Scan** — пакетное обнаружение
- **Batch Segmentation** — пакетная сегментация
- **Change Detection** — сравнение до/после
- Scheduled scans
- Real-time progress
- Per-file results
- Bulk export

### Поддерживаемые форматы

| Тип | Форматы |
|-----|---------|
| Изображения | JPG, PNG, BMP, TIFF |
| Видео | MP4, MOV, AVI |
| Экспорт | CSV, JSON, YOLO, COCO |

## Network v3.3

### Возможности

- Hub+client topology
- JWT authentication
- 6 WebSocket channels (N1-N6)
- Target exchange
- Chat functionality
- Location sharing
- File synchronization
- IP filtering

### WebSocket Channels

| Channel | Name | Описание |
|---------|------|----------|
| N1 | status | Статус узлов |
| N2 | detections | Результаты обнаружения |
| N3 | segments | Данные сегментации |
| N4 | chat | Сообщения |
| N5 | files | Файлы |
| N6 | location | Геолокация |

## AI Analyst (Ollama)

### Возможности

- Локальные LLM (llama3.2, mistral-nemo)
- Rules engine (custom rules)
- Alerts (critical, warning, info)
- Session trace
- Health scoring
- Species identification
- Recommendations

### Models

| Model | VRAM | Speed | Accuracy |
|-------|------|-------|----------|
| phi3-mini | 2 GB | 2s | Средняя |
| llama3.2 | 4 GB | 5s | Высокая |
| mistral-nemo | 6 GB | 8s | Максимальная |

## Portable Version

### Возможности

- Standalone distribution
- Air-gap compatible
- USB deployment
- No installation required
- All features included

### Package size

| Component | Size |
|-----------|------|
| Minimal | 500 MB |
| Standard | 2 GB |
| Full | 4.4 GB |

## Comparison Table

| Feature | Detection | Segmentation | 3D Recon | Batch | Network | AI |
|---------|-----------|--------------|----------|-------|---------|-----|
| **GPU Required** | Recommended | Recommended | Required | Recommended | No | Recommended |
| **Min VRAM** | 4 GB | 4 GB | 8 GB | 4 GB | - | 4 GB |
| **Speed** | Fast | Medium | Slow | Fast | N/A | Medium |
| **Accuracy** | High | Very High | High | High | N/A | High |

## Дальнейшие шаги

1. **[Operator Guide](../01-OPERATOR/OVERVIEW.md)** — использование
2. **[Engineer Guide](../02-ENGINEER/OVERVIEW.md)** — развёртывание
3. **[Developer Guide](../03-DEVELOPER/OVERVIEW.md)** — разработка
4. **[Reference](../05-REFERENCE/OVERVIEW.md)** — справочник

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
