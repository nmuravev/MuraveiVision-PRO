# Database — MuraveiVision PRO

> **База данных: schema, миграции, WAL mode, оптимизация.**

## Обзор

MuraveiVision PRO использует SQLite с WAL (Write-Ahead Logging) режимом для высокой производительности при конкурентном доступе.

## Database Configuration

```yaml
# config/custom.yaml
database:
  url: "sqlite:///data/muravei.db"
  wal_mode: true
  timeout: 30
  busy_timeout: 5000
  max_connections: 10
  auto_vacuum:
    enabled: true
    interval_days: 7
```

## Schema

### Tables

```
Database: muravei.db
├── sessions              (session metadata)
├── detections            (detection results)
├── segments              (segmentation masks)
├── models                (model registry)
├── users                 (user accounts)
├── network_peers         (network nodes)
├── chat_messages         (chat history)
└── session_trace         (session events)
```

### 1. sessions

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active',
    media_files INTEGER DEFAULT 0,
    gps_lat REAL,
    gps_lon REAL,
    gps_alt REAL,
    notes TEXT,
    metadata TEXT  -- JSON
);

CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_created ON sessions(created_at);
```

**Поля:**
- `id` — UUID, primary key
- `name` — имя сессии
- `status` — active, completed, archived
- `gps_lat/lon/alt` — координаты начала сессии
- `metadata` — JSON с дополнительными данными

### 2. detections

```sql
CREATE TABLE detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    class_id INTEGER NOT NULL,
    class_name TEXT NOT NULL,
    confidence REAL NOT NULL,
    bbox_x1 INTEGER NOT NULL,
    bbox_y1 INTEGER NOT NULL,
    bbox_x2 INTEGER NOT NULL,
    bbox_y2 INTEGER NOT NULL,
    mask_id INTEGER,
    timestamp TIMESTAMP,
    gps_lat REAL,
    gps_lon REAL,
    processing_time_ms INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (mask_id) REFERENCES segments(id)
);

CREATE INDEX idx_detections_session ON detections(session_id);
CREATE INDEX idx_detections_class ON detections(class_id);
CREATE INDEX idx_detections_file ON detections(file_name);
```

**Поля:**
- `session_id` — foreign key к sessions
- `class_id` — ID класса из class_catalog
- `class_name` — имя класса (дублируется для скорости)
- `confidence` — confidence score (0.0-1.0)
- `bbox_*` — bounding box coordinates
- `mask_id` — foreign key к segments (если есть)

### 3. segments

```sql
CREATE TABLE segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    detection_id INTEGER,
    file_name TEXT NOT NULL,
    mask_path TEXT NOT NULL,
    polygon TEXT,  -- JSON array of points
    area_pixels INTEGER,
    area_cm2 REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (detection_id) REFERENCES detections(id)
);

CREATE INDEX idx_segments_session ON segments(session_id);
CREATE INDEX idx_segments_file ON segments(file_name);
```

**Поля:**
- `mask_path` — путь к PNG маске
- `polygon` — JSON массив точек контура
- `area_pixels` — площадь в пикселях
- `area_cm2` — площадь в см² (если калибрована)

### 4. models

```sql
CREATE TABLE models (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,  -- detection, segmentation, depth
    version TEXT NOT NULL,
    path TEXT NOT NULL,
    size_mb REAL,
    checksum TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_models_type ON models(type);
CREATE INDEX idx_models_active ON models(is_active);
```

**Поля:**
- `type` — detection, segmentation, depth
- `is_active` — 1 = текущая модель
- `checksum` — SHA256 для верификации

### 5. users

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'operator',  -- operator, engineer, admin
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active INTEGER DEFAULT 1
);

CREATE INDEX idx_users_username ON users(username);
```

**Поля:**
- `password_hash` — bcrypt hash
- `role` — operator, engineer, admin

### 6. network_peers

```sql
CREATE TABLE network_peers (
    id TEXT PRIMARY KEY,
    client_id TEXT UNIQUE NOT NULL,
    client_secret TEXT NOT NULL,
    status TEXT DEFAULT 'offline',
    last_seen TIMESTAMP,
    host TEXT,
    port INTEGER,
    detections_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_peers_status ON network_peers(status);
```

### 7. chat_messages

```sql
CREATE TABLE chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    sender_id TEXT NOT NULL,
    sender_name TEXT NOT NULL,
    message TEXT NOT NULL,
    message_type TEXT DEFAULT 'text',  -- text, system, alert
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_chat_session ON chat_messages(session_id);
CREATE INDEX idx_chat_timestamp ON chat_messages(timestamp);
```

### 8. session_trace

```sql
CREATE TABLE session_trace (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    event_data TEXT,  -- JSON
    duration_ms INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_trace_session ON session_trace(session_id);
CREATE INDEX idx_trace_timestamp ON session_trace(timestamp);
CREATE INDEX idx_trace_type ON session_trace(event_type);
```

**event_type:**
- `session_start`
- `media_loaded`
- `detection_started`
- `detection_completed`
- `segmentation_started`
- `alert_generated`
- `session_end`

## WAL Mode

### Что такое WAL

```
WAL (Write-Ahead Logging):

Обычный SQLite:
┌────────┐  write  ┌────────┐
│ Reader │──wait──→│ Writer │  ← Reader блокируется

WAL mode:
┌────────┐              ┌────────┐
│ Reader │──read──→│ WAL file │  ← Reader не блокируется
└────────┘              └────────┘
                          │
                          ▼
                      ┌────────┐
                      │  Main  │
                      │  DB    │
                      └────────┘
```

### Включение

```python
# database.py
import sqlite3

def get_connection():
    conn = sqlite3.connect("data/muravei.db")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA cache_size=-64000")  # 64 MB
    return conn
```

### Преимущества

| Параметр | Обычный | WAL |
|----------|---------|-----|
| Read during write | ❌ Блокируется | ✅ Разрешено |
| Write during read | ❌ Блокируется | ✅ Разрешено |
| Performance | Средняя | Высокая |
| Concurrency | Низкая | Высокая |

## Migrations

### Migration system

```python
# scripts/migrate_db.py
import sqlite3
from pathlib import Path

MIGRATIONS = {
    "3.0.0": [
        "CREATE TABLE sessions (...)",
        "CREATE TABLE detections (...)",
        # ...
    ],
    "3.1.0": [
        "ALTER TABLE sessions ADD COLUMN gps_lat REAL",
        "CREATE TABLE network_peers (...)",
    ],
    "3.2.0": [
        "CREATE TABLE session_trace (...)",
        "ALTER TABLE detections ADD COLUMN processing_time_ms INTEGER",
    ]
}

def migrate_db(target_version="3.2.0"):
    conn = get_connection()
    current = get_current_version(conn)
    
    for version, statements in MIGRATIONS.items():
        if version > current and version <= target_version:
            for stmt in statements:
                conn.execute(stmt)
            set_version(conn, version)
            print(f"[OK] Applied migration: {version}")
    
    conn.commit()
    conn.close()
```

### Running migrations

```bash
# Auto migration on startup
python backend/scripts/migrate_db.py

# Manual migration
python backend/scripts/migrate_db.py --version 3.2.0

# Rollback (if available)
python backend/scripts/migrate_db.py --rollback
```

## Optimization

### Indexes

```sql
-- Critical indexes for performance
CREATE INDEX idx_detections_session ON detections(session_id);
CREATE INDEX idx_detections_class ON detections(class_id);
CREATE INDEX idx_detections_file ON detections(file_name);
CREATE INDEX idx_segments_session ON segments(session_id);
CREATE INDEX idx_trace_session ON session_trace(session_id);
CREATE INDEX idx_trace_type ON session_trace(event_type);
```

### Vacuum

```bash
# Reclaim space
muravei_env\Scripts\python.exe backend/scripts/db_vacuum.py

# Optimize indexes
muravei_env\Scripts\python.exe backend/scripts/db_optimize.py
```

### Size monitoring

```bash
# Check database size
muravei_env\Scripts\python.exe backend/scripts/db_size.py

# Output:
# muravei.db: 45 MB
# ├── sessions: 12 MB
# ├── detections: 20 MB
# ├── segments: 8 MB
# └── other: 5 MB
```

## Backup

### Automated backup

```yaml
# config/backup.yaml
backup:
  enabled: true
  interval_hours: 24
  retention_days: 30
  destination: "data/backups/"
  compress: true
```

### Manual backup

```bash
# Full backup
muravei_env\Scripts\python.exe backend/scripts/backup.py --full

# Database only
muravei_env\Scripts\python.exe backend/scripts/backup.py --db

# Restore
muravei_env\Scripts\python.exe backend/scripts/backup.py \
  --restore --file data/backups/muravei_20260919.db.gz
```

## Troubleshooting

### Проблема: Database locked

```
SQLite database is locked
Solution:
1. Проверьте WAL mode: PRAGMA journal_mode;
2. Увеличьте busy_timeout: PRAGMA busy_timeout=5000;
3. Закройте другие подключения
4. Запустите: db_vacuum.py
```

### Проблема: Database corrupt

```
Database corruption detected
Solution:
1. Восстановите из backup
2. Проверьте целостность: db_check.py
3. Попробуйте: sqlite3 muravei.db ".recover" | sqlite3 recovered.db
```

## Дальнейшие шаги

1. **[API Reference](./API_REFERENCE.md)** — API endpoints
2. **[Testing](./TESTING.md)** — тестирование
3. **[Debugging](./DEBUGGING.md)** — отладка

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
