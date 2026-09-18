# 3D Reconstruction (DA3) — MuraveiVision PRO

> **3D реконструкция: DA3 Dense Backend (NEW v3.2.0), COLMAP, GSplat, Flight3D.**

## Overview

3D Reconstruction creates three-dimensional models from images using multiple algorithms.

## Methods

| Method | Description | VRAM | Speed | Quality |
|--------|-------------|------|-------|---------|
| **DA3-S** | Depth Anything 3 Small | 2.1 GB | Fast | High |
| **DA3-B** | Depth Anything 3 Base | 4.3 GB | Medium | Very High |
| **COLMAP** | Structure from Motion | 4-8 GB | Slow | Very High |
| **GSplat** | Gaussian Splatting | 6-12 GB | Medium | Excellent |
| **Flight3D** | Aerial reconstruction | 8-12 GB | Slow | Excellent |

## DA3 Dense Backend (NEW v3.2.0)

Depth Anything 3 provides dense depth estimation from single images.

```
DA3 Pipeline:
Input Image (RGB)
    ↓
DA3 Model (encoder + decoder)
    ↓
Depth Map (per-pixel depth)
    ↓
Point Cloud Generation
    ↓
Mesh Reconstruction
```

### DA3 Variants

| Variant | Size | VRAM | Quality |
|---------|------|------|---------|
| DA3-S | 2.1 GB | 2.1 GB | High |
| DA3-B | 4.3 GB | 4.3 GB | Very High |

### API Example

```bash
curl -X POST http://localhost:8000/api/reconstruct/3d \
  -F "image=@IMG_001.jpg" \
  -F "method=da3" \
  -F "variant=s"

# Response:
{
  "status": "success",
  "method": "da3",
  "depth_map_url": "/data/depth/IMG_001_depth.png",
  "point_cloud_url": "/data/points/IMG_001.ply",
  "processing_time_ms": 3500
}
```

## COLMAP

Structure from Motion for multiple images.

```
COLMAP Pipeline:
Multiple Images (overlapping)
    ↓
Feature Detection (SIFT)
    ↓
Feature Matching
    ↓
Bundle Adjustment
    ↓
Point Cloud + Camera Poses
    ↓
Mesh Generation
```

### Requirements

- 10+ overlapping images
- Good lighting
- Static scene
- 4-8 GB VRAM

## GSplat

Gaussian Splatting for photorealistic reconstruction.

```
GSplat Pipeline:
Multiple Images
    ↓
3D Gaussian Points
    ↓
Optimization (rasterization)
    ↓
Real-time Rendering
```

### Requirements

- 50+ images
- GPU with 6+ GB VRAM
- 5-10 minutes processing

## Export Formats

| Format | Description | Use |
|--------|-------------|-----|
| OBJ | Wavefront OBJ | 3D printing |
| PLY | Point cloud | Analysis |
| GLB | glTF Binary | Web viewing |
| FBX | Autodesk FBX | Game engines |

## Версия

- **Приложение:** v3.2.0
