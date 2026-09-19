# API Reference — MuraveiVision PRO

> **Полная документация всех REST API endpoints с curl примерами.**

## Обзор

API base URL: `http://localhost:8000/api`

Authentication: Bearer token в заголовке `Authorization`.

## Authentication

### Login

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "your-password"
  }'

# Response 200:
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

### Refresh Token

```bash
curl -X POST http://localhost:8000/api/auth/refresh \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."

# Response 200:
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

### Health Check

```bash
curl http://localhost:8000/health

# Response 200:
{
  "status": "healthy",
  "version": "3.2.0",
  "gpu": {
    "available": true,
    "device": "cuda",
    "memory_used_mb": 2048
  },
  "database": {
    "writable": true,
    "size_mb": 45
  }
}
```

## Detection API

### Single Image Detection

```bash
curl -X POST http://localhost:8000/api/detect \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -F "image=@IMG_001.jpg" \
  -F "model=yolo26s-ft" \
  -F "sahi_enabled=true" \
  -F "slice_height=512" \
  -F "slice_width=512" \
  -F "overlap=0.2" \
  -F "threshold=0.5" \
  -F "iou=0.45"

# Response 200:
{
  "status": "success",
  "detections": [
    {
      "id": 1,
      "class": "ant_worker",
      "confidence": 0.95,
      "bbox": [120, 45, 180, 95],
      "mask_path": null
    },
    {
      "id": 2,
      "class": "cricket",
      "confidence": 0.87,
      "bbox": [340, 210, 380, 250],
      "mask_path": null
    }
  ],
  "processing_time_ms": 245,
  "model": "yolo26s-ft"
}
```

### Batch Detection

```bash
curl -X POST http://localhost:8000/api/detect/batch \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -F "folder=@/data/field_session_01/" \
  -F "model=yolo26s-ft" \
  -F "recursive=true" \
  -F "sahi_enabled=true"

# Response 200:
{
  "status": "success",
  "job_id": "batch_20260919_001",
  "total_files": 156,
  "processed": 156,
  "failed": 0,
  "total_detections": 1247,
  "processing_time_ms": 45230,
  "results_url": "/api/detect/batch/batch_20260919_001/results"
}
```

### Get Detection Results

```bash
curl http://localhost:8000/api/detect/batch/batch_20260919_001/results \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."

# Response 200:
{
  "job_id": "batch_20260919_001",
  "status": "completed",
  "progress": 100,
  "files": [
    {
      "file": "IMG_001.jpg",
      "detections": 5,
      "processing_time_ms": 245
    }
  ]
}
```

### Export Detections

```bash
curl -X POST http://localhost:8000/api/detect/export \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -H "Content-Type: application/json" \
  -d '{
    "format": "coco",
    "session_id": "field_session_01",
    "include_masks": true
  }'

# Response 200:
{
  "status": "success",
  "export_path": "/data/exports/coco_field_session_01.json",
  "format": "coco",
  "size_mb": 2.3
}
```

## Segmentation API

### Interactive Segmentation

```bash
curl -X POST http://localhost:8000/api/segment/interactive \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -F "image=@IMG_001.jpg" \
  -F "tool=point" \
  -F "point_x=250" \
  -F "point_y=180"

# Response 200:
{
  "status": "success",
  "segment_id": "seg_001",
  "mask_url": "/data/masks/IMG_001_seg1.png",
  "polygon": [[250, 180], [260, 175], [270, 185]],
  "area_pixels": 1245,
  "area_cm2": 0.12
}
```

### Rectangle Segmentation

```bash
curl -X POST http://localhost:8000/api/segment/interactive \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -F "image=@IMG_001.jpg" \
  -F "tool=rectangle" \
  -F "x1=100" \
  -F "y1=50" \
  -F "x2=300" \
  -F "y2=250"

# Response 200:
{
  "status": "success",
  "segment_id": "seg_002",
  "mask_url": "/data/masks/IMG_001_seg2.png",
  "area_pixels": 5678
}
```

### Propagate Segmentation

```bash
curl -X POST http://localhost:8000/api/segment/propagate \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -F "video=video_001.mp4" \
  -F "source_frame=300" \
  -F "speed=balanced" \
  -F "smoothing=true"

# Response 202:
{
  "status": "processing",
  "job_id": "prop_20260919_001",
  "total_frames": 27000,
  "estimated_time_seconds": 540
}

# Check progress:
curl http://localhost:8000/api/segment/propagate/prop_20260919_001

# Response 200:
{
  "job_id": "prop_20260919_001",
  "status": "processing",
  "progress": 45,
  "processed_frames": 12150,
  "total_frames": 27000
}
```

### Batch Segmentation

```bash
curl -X POST http://localhost:8000/api/segment/batch \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -F "folder=@/data/field_session_01/" \
  -F "model=sam3" \
  -F "method=auto"

# Response 200:
{
  "status": "success",
  "job_id": "seg_batch_001",
  "total_files": 156,
  "processed": 156,
  "total_segments": 423
}
```

## AI Analysis API

### Run Analysis

```bash
curl -X POST http://localhost:8000/api/ai/analyze \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "field_session_01",
    "objects": [
      {"class": "ant_worker", "confidence": 0.95, "bbox": [120,45,180,95]},
      {"class": "ant_queen", "confidence": 0.92, "bbox": [340,210,380,250]}
    ],
    "rules": ["high_density", "predator_detected", "colony_healthy"],
    "template": "species_identification"
  }'

# Response 200:
{
  "status": "success",
  "analysis": {
    "health_score": 85,
    "health_status": "Good",
    "alerts": [
      {
        "level": "warning",
        "type": "high_density",
        "message": "Ant density 67/m² exceeds threshold"
      }
    ],
    "recommendations": [
      "Monitor colony growth rate",
      "Check for predator activity"
    ]
  }
}
```

### Create Rule

```bash
curl -X POST http://localhost:8000/api/ai/rules \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Low worker count",
    "condition": "ant_worker < 10",
    "action": "alert",
    "level": "critical",
    "message": "CRITICAL: Low worker count detected"
  }'

# Response 201:
{
  "status": "created",
  "rule_id": "rule_001",
  "name": "Low worker count"
}
```

### Get Alerts

```bash
curl http://localhost:8000/api/ai/alerts?level=critical \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."

# Response 200:
{
  "alerts": [
    {
      "id": "alert_001",
      "level": "critical",
      "type": "predator_detected",
      "message": "Spider detected near ant colony",
      "timestamp": "2026-09-19T10:23:45Z",
      "acknowledged": false
    }
  ]
}
```

## Batch Operations API

### Start Batch Scan

```bash
curl -X POST http://localhost:8000/api/batch/scan \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -F "folder=@/data/field_session_01/" \
  -F "mode=detection" \
  -F "model=yolo26s-ft" \
  -F "recursive=true"

# Response 202:
{
  "status": "processing",
  "job_id": "batch_scan_001",
  "total_files": 156,
  "estimated_time_seconds": 300
}
```

### Get Batch Progress

```bash
curl http://localhost:8000/api/batch/scan/batch_scan_001 \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIds..."

# Response 200:
{
  "job_id": "batch_scan_001",
  "status": "processing",
  "progress": 78,
  "processed_files": 122,
  "total_files": 156,
  "total_detections": 987,
  "failed_files": 0,
  "current_file": "IMG_0123.jpg"
}
```

### Change Detection

```bash
curl -X POST http://localhost:8000/api/batch/change-detect \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -H "Content-Type: application/json" \
  -d '{
    "before_folder": "/data/before_fire/",
    "after_folder": "/data/after_fire/",
    "matching": "by_gps",
    "threshold": 0.70
  }'

# Response 200:
{
  "status": "success",
  "pairs_compared": 89,
  "pairs_matched": 85,
  "changes_detected": 23,
  "change_map_url": "/data/changes/change_map_001.png"
}
```

## Network API

### Get Network Status

```bash
curl http://localhost:8000/api/network/status \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."

# Response 200:
{
  "mode": "hub",
  "connected_clients": 3,
  "clients": [
    {
      "id": "client_01",
      "status": "online",
      "last_seen": "2026-09-19T12:00:00Z",
      "detections_count": 247
    }
  ]
}
```

### Send Chat Message

```bash
curl -X POST http://localhost:8000/api/network/chat \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -H "Content-Type: application/json" \
  -d '{
    "message": " Colony looks healthy today",
    "type": "text"
  }'

# Response 200:
{
  "status": "sent",
  "message_id": "msg_001",
  "timestamp": "2026-09-19T12:05:00Z"
}
```

### Share Location

```bash
curl -X POST http://localhost:8000/api/network/location \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIds..." \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 55.7558,
    "longitude": 37.6173,
    "altitude": 156,
    "accuracy": 5
  }'

# Response 200:
{
  "status": "shared",
  "timestamp": "2026-09-19T12:10:00Z"
}
```

## Database API

### Get Sessions

```bash
curl http://localhost:8000/api/sessions \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIds..."

# Response 200:
{
  "sessions": [
    {
      "id": "sess_001",
      "name": "field_session_01",
      "created_at": "2026-09-19T10:00:00Z",
      "status": "completed",
      "detections_count": 247,
      "segments_count": 45
    }
  ]
}
```

### Get Session Details

```bash
curl http://localhost:8000/api/sessions/sess_001 \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIds..."

# Response 200:
{
  "id": "sess_001",
  "name": "field_session_01",
  "created_at": "2026-09-19T10:00:00Z",
  "status": "completed",
  "media_files": 156,
  "detections": 247,
  "segments": 45,
  "gps_points": 1234
}
```

## Error Responses

### Common Error Codes

| Code | Описание | Решение |
|------|----------|---------|
| 400 | Bad Request | Проверьте параметры запроса |
| 401 | Unauthorized | Проверьте token |
| 403 | Forbidden | Нет прав |
| 404 | Not Found | Ресурс не найден |
| 429 | Rate Limited | Подождите |
| 500 | Internal Error | Проверьте logs |

### Error Response Format

```json
{
  "error": {
    "code": 400,
    "message": "Invalid slice size",
    "details": "slice_height must be between 256 and 2048"
  }
}
```

## WebSocket API

### Connect

```javascript
const ws = new WebSocket('ws://localhost:8765');

ws.onopen = () => {
  // Subscribe to channels
  ws.send(JSON.stringify({
    action: 'subscribe',
    channels: ['status', 'detections']
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log(message.channel, message.data);
};
```

### Message Format

```json
{
  "channel": "detections",
  "type": "new_detections",
  "data": {
    "session_id": "sess_001",
    "file": "IMG_001.jpg",
    "detections": [
      {"class": "ant_worker", "confidence": 0.95}
    ]
  },
  "timestamp": "2026-09-19T12:00:00Z"
}
```

## Дальнейшие шаги

1. **[Database](./DATABASE.md)** — schema и миграции
2. **[Testing](./TESTING.md)** — стратегии тестирования
3. **[Debugging](./DEBUGGING.md)** — отладка

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
