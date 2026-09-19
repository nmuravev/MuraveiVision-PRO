# Database Schema — MuraveiVision PRO

> **Схема базы данных SQLite (muravei.db).**

## Обзор

База данных `muravei.db` хранит PIN-коды ролей, настройки, результаты обнаружения (detections), маски сегментации, сетевую конфигурацию и служебные таблицы.

**Конфигурация SQLite:**
- Journal mode: `WAL` (Write-Ahead Logging)
- Foreign keys: включены
- Auto-checkpoint: 1000 страниц (~8 MB)

## Таблицы

### 1. pins

Хранит PIN-коды авторизации по ролям (SHA256 + base64).

```sql
CREATE TABLE pins (
    role TEXT PRIMARY KEY,
    pin_sha256 TEXT NOT NULL,
    pin_b64 TEXT NOT NULL,
    updated_at REAL NOT NULL
);
```

**PIN-коды по умолчанию:**

| Роль | PIN | Описание |
|------|-----|----------|
| `operator` | `1234567` | Оператор |
| `engineer` | `0000000` | Инженер |
| `master` | `0987907` | Мастер |

**Функции:** `get_pin_role()`, `find_role_by_pin()`, `update_pin()`, `list_pin_roles()`

### 2. settings

Ключ-значение для настроек приложения.

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

**Ключи:**
- `jwt_secret` — секрет JWT-токена (генерируется при инициализации)
- `schema_version` — версия схемы БД

**Функции:** `get_setting()`, `set_setting()`, `get_jwt_secret()`

### 3. lockouts

Блокировка клиентов после неудачных попыток входа.

```sql
CREATE TABLE lockouts (
    client_key TEXT PRIMARY KEY,
    fail_count INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0
);
```

**Параметры:** `MAX_LOCKOUT_RETRIES = 3`, `max_fails = 5`, `lock_sec = 120`

**Функции:** `get_lockout()`, `record_failed_login()`, `clear_lockout()`

### 4. detections

Результаты обнаружения объектов YOLO.

```sql
CREATE TABLE detections (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    source_video TEXT NOT NULL,
    time_sec REAL NOT NULL,
    frame_idx INTEGER NOT NULL DEFAULT 0,
    class_id INTEGER NOT NULL DEFAULT 0,
    class_name TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    bbox_x REAL NOT NULL,
    bbox_y REAL NOT NULL,
    bbox_w REAL NOT NULL,
    bbox_h REAL NOT NULL,
    crop_path TEXT,
    is_edited INTEGER NOT NULL DEFAULT 0,
    edited_by TEXT,
    edited_at REAL,
    user_notes TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    origin TEXT NOT NULL DEFAULT 'auto',
    ai_class_name TEXT,
    gps_lat REAL,
    gps_lon REAL,
    gps_alt REAL
);

CREATE INDEX idx_det_source_time ON detections(source_video, time_sec);
CREATE INDEX idx_det_class ON detections(class_name);
CREATE INDEX idx_det_notes ON detections(user_notes);
CREATE INDEX idx_det_created ON detections(created_at DESC);
```

**Функции:** `insert_detection()`, `get_detection()`, `list_detections()`, `update_detection()`, `soft_delete_detection()`, `save_crop_jpeg()`

### 5. network_config

Конфигурация сетевых соединений.

```sql
CREATE TABLE network_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    mode TEXT NOT NULL DEFAULT 'off',
    server_ip TEXT NOT NULL DEFAULT '127.0.0.1',
    port INTEGER NOT NULL DEFAULT 8000,
    base_name TEXT NOT NULL DEFAULT 'База-1',
    updated_at REAL NOT NULL,
    hub_pin TEXT,
    base_id TEXT,
    lan_beacon_enabled TEXT DEFAULT '0',
    lan_beacon_port INTEGER DEFAULT 8001
);
```

### 6. network_bases

Зарегистрированные сетевые базы.

```sql
CREATE TABLE network_bases (
    id TEXT PRIMARY KEY,
    base_name TEXT NOT NULL,
    ip TEXT NOT NULL,
    last_seen REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'online'
);
```

### 7. network_targets

Сетевые цели для передачи.

```sql
CREATE TABLE network_targets (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    direction TEXT NOT NULL,
    class_name TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    gps_lat REAL,
    gps_lon REAL,
    crop_path TEXT,
    source_base TEXT,
    source_video TEXT,
    notes TEXT,
    expires_at REAL,
    synced_at REAL
);

CREATE INDEX idx_net_targets_created ON network_targets(created_at DESC);
CREATE INDEX idx_net_targets_synced ON network_targets(synced_at);
```

### 8. network_messages

Сетевые сообщения.

```sql
CREATE TABLE network_messages (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    direction TEXT NOT NULL,
    sender TEXT NOT NULL,
    body TEXT NOT NULL,
    expires_at REAL,
    synced_at REAL,
    attachment_id TEXT
);

CREATE INDEX idx_net_messages_created ON network_messages(created_at DESC);
CREATE INDEX idx_net_messages_synced ON network_messages(synced_at);
```

### 9. class_overrides

Переопределение названий и параметров классов.

```sql
CREATE TABLE class_overrides (
    class_id INTEGER PRIMARY KEY,
    name_ru TEXT NOT NULL DEFAULT '',
    aliases TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    in_prompt INTEGER NOT NULL DEFAULT 0,
    confidence_threshold REAL,
    updated_at REAL NOT NULL
);
```

**Функции:** `get_class_override()`, `upsert_class_override()`, `delete_class_override()`, `list_class_overrides()`

### 10. excluded_classes

Исключённые классы (COCO DROP + пользовательские).

```sql
CREATE TABLE excluded_classes (
    class_name TEXT PRIMARY KEY,
    added_at REAL NOT NULL DEFAULT 0
);
```

**Функции:** `list_excluded_classes()`, `upsert_excluded_class()`, `delete_excluded_class()`

### 11. flight_tracks

Треки полётов (JSON).

```sql
CREATE TABLE flight_tracks (
    id TEXT PRIMARY KEY,
    video_path TEXT NOT NULL UNIQUE,
    track_data TEXT NOT NULL DEFAULT '[]',
    source_file TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX idx_flight_tracks_video ON flight_tracks(video_path);
```

**Функции:** `upsert_flight_track()`, `get_flight_track()`

### 12. active_learning_samples

Образцы для активного обучения.

```sql
CREATE TABLE active_learning_samples (
    id TEXT PRIMARY KEY,
    detection_id TEXT NOT NULL,
    source_video TEXT NOT NULL,
    time_sec REAL NOT NULL,
    feedback_type TEXT NOT NULL,
    proposed_class TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(detection_id, feedback_type)
);

CREATE INDEX idx_active_learning_status ON active_learning_samples(status, created_at DESC);
```

**Статусы:** `pending`, `accepted`, `rejected`

**Функции:** `enqueue_active_learning()`, `list_active_learning_samples()`, `decide_active_learning_sample()`

### 13. detection_embeddings

Эмбеддинги обнаружений для similarity search.

```sql
CREATE TABLE detection_embeddings (
    detection_id TEXT PRIMARY KEY,
    method TEXT NOT NULL,
    crop_mtime REAL NOT NULL,
    dim INTEGER NOT NULL,
    embedding BLOB NOT NULL,
    computed_at REAL NOT NULL
);
```

**Функции:** `get_embedding()`, `upsert_embedding()`, `delete_embedding()`

### 14. seg_masks

Маски сегментации (SAM/polygon).

```sql
CREATE TABLE seg_masks (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    source_video TEXT NOT NULL,
    time_sec REAL NOT NULL,
    frame_idx INTEGER NOT NULL DEFAULT 0,
    class_name TEXT NOT NULL DEFAULT 'object',
    confidence REAL NOT NULL DEFAULT 1.0,
    polygon_json TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'sam3',
    track_id TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_seg_masks_source_time ON seg_masks(source_video, time_sec);
CREATE INDEX idx_seg_masks_track ON seg_masks(track_id);
```

**Функции:** `insert_seg_masks_batch()`, `list_seg_masks()`, `soft_delete_seg_masks_by_track()`

## Связи

```
pins — авторизация по ролям
settings — глобальные настройки
lockouts — защита от брутфорса
detections — основной рабочий столбец
  └─ seg_masks — маски сегментации (1:N по source_video)
network_* — сетевая подсистема (config, bases, targets, messages)
class_overrides — переопределение классов
excluded_classes — исключённые классы
flight_tracks — треки полётов
active_learning_samples — обратная связь для обучения
detection_embeddings — векторные представления
```

## Инициализация

```python
from services.db import init_db
init_db()  # Создаёт схему и seedит PIN-коды при первом вызове
```

## Версия

- **Приложение:** v3.2.0
