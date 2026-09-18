# Segmentation (SAM3) — MuraveiVision PRO

> **Интерактивная и propagate сегментация с SAM3.**

## Overview

SAM3 segmentation provides precise object segmentation using Segment Anything Model 3.

## Modes

### Interactive Mode

Tools:
- **Point** — click on object
- **Rectangle** — drag rectangle
- **Polygon** — draw polygon
- **Freehand** — free drawing

### Propagate Mode

Automatically propagates segmentation across video frames.

```
Propagation:
Frame 1: Draw mask on object
    ↓ propagate
Frame 2-End: Auto-generated masks
```

## Performance (RTX 4070)

| Mode | Resolution | FPS |
|------|------------|-----|
| Interactive | 1920×1080 | 30 |
| Interactive | 3840×2160 | 12 |
| Propagate Fast | 1920×1080 | 100 |
| Propagate Balanced | 1920×1080 | 50 |

## Export Formats

| Format | Description |
|--------|-------------|
| PNG mask | Binary mask image |
| JSON | Metadata + links |
| COCO | Standard format |

## API Example

```bash
# Interactive
curl -X POST http://localhost:8000/api/segment/interactive \
  -F "image=@IMG_001.jpg" \
  -F "tool=point" \
  -F "point_x=250" \
  -F "point_y=180"

# Propagate
curl -X POST http://localhost:8000/api/segment/propagate \
  -F "video=video_001.mp4" \
  -F "source_frame=300" \
  -F "speed=balanced"
```

## Версия

- **Приложение:** v3.2.0
