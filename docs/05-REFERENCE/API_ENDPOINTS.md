# API Endpoints — MuraveiVision PRO

> **Полная документация REST API endpoints.**

## Base URL

`http://localhost:8000/api`

## Authentication

All endpoints require Bearer token except `/auth/login` and `/health`.

```
Authorization: Bearer <token>
```

## Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/login` | Login |
| POST | `/auth/refresh` | Refresh token |
| GET | `/health` | Health check |
| POST | `/detect` | Single detection |
| POST | `/detect/batch` | Batch detection |
| POST | `/detect/export` | Export results |
| POST | `/segment/interactive` | Interactive segmentation |
| POST | `/segment/propagate` | Propagate segmentation |
| POST | `/segment/batch` | Batch segmentation |
| POST | `/ai/analyze` | AI analysis |
| POST | `/ai/rules` | Create rule |
| GET | `/ai/alerts` | Get alerts |
| POST | `/batch/scan` | Start batch scan |
| POST | `/batch/change-detect` | Change detection |
| GET | `/network/status` | Network status |
| POST | `/network/chat` | Send chat message |
| POST | `/network/location` | Share location |
| GET | `/sessions` | List sessions |
| GET | `/sessions/{id}` | Session details |

## Error Responses

```json
{
  "error": {
    "code": 400,
    "message": "Invalid parameter",
    "details": "slice_height must be between 256 and 2048"
  }
}
```

## Версия

- **Приложение:** v3.2.0
