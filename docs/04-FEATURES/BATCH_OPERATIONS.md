# Batch Operations — MuraveiVision PRO

> **Пакетная обработка: Batch Scan, Batch Segmentation, Change Detection.**

## Overview

Batch Operations enable processing of multiple files automatically.

## Batch Scan

Process detections across entire folders.

```
Batch Scan Workflow:
Folder Selection
    ↓
Recursive File Discovery
    ↓
Process Each File
    ↓
Aggregate Results
    ↓
Export (CSV, JSON, COCO)
```

### API Example

```bash
curl -X POST http://localhost:8000/api/batch/scan \
  -F "folder=@/data/field_session_01/" \
  -F "mode=detection" \
  -F "model=yolo8s-ft"

# Response:
{
  "job_id": "batch_scan_001",
  "total_files": 156,
  "status": "processing"
}
```

## Change Detection

Compare "before" and "after" images.

```
Change Detection:
Before Set ─┐
            ├→ Match Pairs → Analyze Changes → Results
After Set  ─┘
```

### Matching Methods

| Method | Description | Accuracy |
|--------|-------------|----------|
| Filename | Exact name match | High |
| GPS | By coordinates | Medium |
| Visual | Similarity score | High |
| Manual | Drag & drop pairs | Perfect |

## Версия

- **Приложение:** v3.2.0
