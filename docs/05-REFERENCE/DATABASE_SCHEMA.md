# Database Schema — MuraveiVision PRO

> **Схема базы данных SQLite.**

## Tables

8 tables: sessions, detections, segments, models, users, network_peers, chat_messages, session_trace.

## Key Relationships

```
sessions 1──N detections
sessions 1──N segments
detections 1──N segments
users 1──N sessions
```

## Версия

- **Приложение:** v3.2.0
