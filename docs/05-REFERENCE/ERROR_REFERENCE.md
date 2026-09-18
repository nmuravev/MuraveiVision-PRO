# Error Reference — MuraveiVision PRO

> **Коды ошибок и способы устранения.**

## HTTP Status Codes

| Code | Meaning | When |
|------|---------|------|
| 200 | OK | Success |
| 201 | Created | Resource created |
| 202 | Accepted | Processing started |
| 400 | Bad Request | Invalid parameters |
| 401 | Unauthorized | Invalid/missing token |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 429 | Too Many Requests | Rate limited |
| 500 | Internal Server Error | Server error |

## Application Error Codes

| Code | Area | Description | Solution |
|------|------|-------------|----------|
| E001 | Backend | Not running | Start backend |
| E002 | Database | Database error | Run db_check.py |
| E003 | GPU | GPU not available | Check CUDA/driver |
| E004 | Model | Model not found | Download model |
| E005 | Storage | Disk space low | Run cleanup.py |
| E006 | Network | Timeout | Check network |
| E007 | WebSocket | Disconnected | Reconnect |
| E008 | Auth | JWT expired | Refresh token |
| E009 | File | File not found | Check path |
| E010 | Format | Invalid format | Convert file |

## Версия

- **Приложение:** v3.2.0
