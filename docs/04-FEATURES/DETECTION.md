# Detection (YOLO/SAHI) — MuraveiVision PRO

> **Обнаружение объектов: YOLO26, SAHI-слайсинг, экспорт результатов.**

## Overview

Detection feature provides object detection using YOLO26 models with SAHI (Slicing Aided Hyper Inference) for large images.

## Supported Models

| Model | Size | Speed | mAP | Use Case |
|-------|------|-------|-----|----------|
| **YOLO26n-ft** | 6 MB | 180 FPS | 37.1 | Fast preview |
| **YOLO26s-ft** | 22 MB | 95 FPS | 44.9 | Field work (recommended) |
| **YOLO26m-ft** | 51 MB | 48 FPS | 50.2 | Detailed analysis |
| **YOLO26l-ft** | 87 MB | 32 FPS | 52.9 | Production |
| **YOLO26n** | 6 MB | 150 FPS | 37.1 | Backup model |

## SAHI Slicing

### What is SAHI?

SAHI divides large images into smaller tiles for better detection of small objects.

```
SAHI Concept:
Original 8192×6144 image:
┌──────────────────────────────────┐
│  Small objects missed!          │
└──────────────────────────────────┘
        ↓ sliced into 512×512
┌───┐───┐───┐
│ 1 │ 2 │ 3 │ ...
└───┘───┘───┘
        ↓ detected
┌─────┐ ┌─────┐
│ Ant │ │Cricket│
└─────┘ └─────┘
        ↓ merged
┌─────┐     ┌─────┐
│ Ant │     │Cricket│
└─────┘     └─────┘
```

### SAHI Parameters

| Parameter | Range | Default | Description |
|-----------|-------|---------|-------------|
| Slice height | 256-2048 | 512 | Tile height in pixels |
| Slice width | 256-2048 | 512 | Tile width in pixels |
| Overlap % | 0-50 | 20 | Overlap between tiles |
| Threshold | 0.1-0.9 | 0.5 | Minimum confidence |
| IoU | 0.1-0.9 | 0.45 | NMS IoU threshold |

### Recommendations

| Scenario | Slice | Overlap | Threshold |
|----------|-------|---------|-----------|
| Small objects | 512×512 | 30% | 0.35 |
| Large objects | 1024×1024 | 10% | 0.50 |
| Fast preview | 1024×1024 | 10% | 0.50 |
| Max accuracy | 512×512 | 30% | 0.30 |

## HUD Exclusion

Auto-blur objects that overlap with HUD elements.

```
HUD Exclusion:
┌──────────────────────┐
│ HUD TOP (info bar)   │
│                      │
│    ┌───┐             │
│    │🐜 │ ← blurred!  │
│    └───┘             │
│                      │
│ HUD BOTTOM (controls)│
└──────────────────────┘
```

## Export Formats

| Format | Extension | Use Case |
|--------|-----------|----------|
| CSV | `.csv` | Excel, analysis |
| JSON | `.json` | API, integrations |
| YOLO | `.txt` | Re-training |
| COCO | `.json` | Publishing |

## API Example

```bash
curl -X POST http://localhost:8000/api/detect \
  -F "image=@IMG_001.jpg" \
  -F "model=yolo26s-ft" \
  -F "sahi_enabled=true" \
  -F "slice_height=512" \
  -F "threshold=0.5"

# Response:
{
  "status": "success",
  "detections": [
    {"class": "ant_worker", "confidence": 0.95, "bbox": [120,45,180,95]}
  ]
}
```

## Версия

- **Приложение:** v3.2.0
