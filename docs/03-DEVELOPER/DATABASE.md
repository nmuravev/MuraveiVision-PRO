# Database — MuraveiVision PRO

> **База данных: структура, функции, WAL mode, оптимизация.**

## Обзор

MuraveiVision PRO использует SQLite (`muravei.db`) с WAL (Write-Ahead Logging) режимом. Все операции инкапсулированы в `backend/services/db.py`.

## Database Configuration

**Путь к БД:** `BASE_DIR/muravei.db`

**Параметры подключения:**
```python
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")
conn.execute("PRAGMA wal_autocheckpoint=1000")  # ~8 MB
```

**Блокировки:**
- `_write_lock` — для всех WRITE-операций (INSERT/UPDATE/DELETE)
- `_lock` — для инициализации схемы (thread-safe singleton)
- READ-операции могут работать конкурентно в WAL mode

## Schema

### Таблицы (14 штук)

```
Database: muravei.db
├── pins                    — PIN-коды авторизации
├── settings                — настройки (key-value)
├── lockouts                — блокировки клиентов
├── detections              — результаты обнаружения
├── network_config          — конфигурация сети
├── network_bases           — сетевые базы
├── network_targets         — сетевые цели
├── network_messages        — сетевые сообщения
├── class_overrides         — переопределение классов
├── excluded_classes        — исключённые классы
├── flight_tracks           — треки полётов
├── active_learning_samples — активное обучение
├── detection_embeddings    — эмбеддинги
└── seg_masks               — маски сегментации
```

### Основные таблицы

#### pins

```sql
CREATE TABLE pins (
    role TEXT PRIMARY KEY,
    pin_sha256 TEXT NOT NULL,
    pin_b64 TEXT NOT NULL,
    updated_at REAL NOT NULL
);
```

Хранит PIN-коды в зашифрованном виде (SHA256 + base64).

**Функции:**
- `get_pin_role(role)` — получить строку PIN по роли
- `find_role_by_pin(pin)` — найти роль по PIN
- `update_pin(role, pin)` — обновить PIN
- `list_pin_roles()` — список всех ролей

#### settings

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

Хранит настройки приложения. Ключ `jwt_secret` создаётся автоматически при инициализации.

**Функции:**
- `get_setting(key, default)` — получить настройку
- `set_setting(key, value)` — установить настройку
- `get_jwt_secret()` — получить секрет JWT

#### lockouts

```sql
CREATE TABLE lockouts (
    client_key TEXT PRIMARY KEY,
    fail_count INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0
);
```

Защита от брутфорса. Блокировка после 5 неудачных попыток на 120 секунд.

**Функции:**
- `get_lockout(client_key)` — получить статус блокировки
- `record_failed_login(client_key, max_fails, lock_sec)` —record неудачную попытку (atomic)
- `clear_lockout(client_key)` — снять блокировку

#### detections

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
```

Основная таблица результатов обнаружения.

**Индексы:**
- `idx_det_source_time` — по видео и времени
- `idx_det_class` — по классу
- `idx_det_notes` — по заметкам
- `idx_det_created` — по дате (DESC)

**Функции:**
- `insert_detection(payload)` — вставить обнаружение
- `get_detection(det_id)` — получить по ID
- `list_detections(source_video, class_name, q, include_deleted)` — список с фильтрами
- `update_detection(det_id, fields)` — обновление ( whitelist columns)
- `soft_delete_detection(det_id, edited_by)` — мягкое удаление
- `save_crop_jpeg(detection_id, jpeg_bytes, bbox)` — сохранить crop
- `soft_delete_detections_for_source(source_video, edited_by)` — удалить все для видео

#### seg_masks

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
```

Маски сегментации (полигоны SAM).

**Функции:**
- `insert_seg_masks_batch(rows)` — batch insert
- `list_seg_masks(source_video, time_from, time_to, track_id, limit)` — список
- `soft_delete_seg_masks_by_track(track_id)` — удалить по треку

#### Остальные таблицы

- **network_config** — конфигурация сети (mode, ip, port, base_name)
- **network_bases** — зарегистрированные базы (status: online/offline)
- **network_targets** — цели для передачи (direction, class, gps)
- **network_messages** — сетевые сообщения (direction, sender, body)
- **class_overrides** — переопределение классов (name_ru, aliases, confidence_threshold)
- **excluded_classes** — исключённые классы (COCO DROP + пользовательские)
- **flight_tracks** — треки полётов (JSON в поле track_data)
- **active_learning_samples** — образцы для обучения (status: pending/accepted/rejected)
- **detection_embeddings** — эмбеддинги (method, dim, embedding BLOB)

## Инициализация

```python
from services.db import init_db
init_db()  # Вызывается автоматически при первом обращении к БД
```

Создаёт схему (CREATE TABLE IF NOT EXISTS) и seedит:
- PIN-коды по умолчанию (`pins`)
- JWT-секрет (`settings.jwt_secret`)
- Сетевую конфигурацию (`network_config`)
- Исключённые классы (`excluded_classes` — COCO DROP)

## Использование

### Пример: обнаружение

```python
from services.db import insert_detection, list_detections

# Вставить обнаружение
det = insert_detection({
    "source_video": "archive/video.mp4",
    "time_sec": 12.5,
    "class_name": "ant_worker",
    "confidence": 0.95,
    "bbox_x": 0.1, "bbox_y": 0.2,
    "bbox_w": 0.05, "bbox_h": 0.05
})

# Получить список
dets = list_detections(
    source_video="video.mp4",
    class_name="ant_worker",
    q="нота"
)
```

### Пример: PIN-коды

```python
from services.db import find_role_by_pin, update_pin

# Проверить PIN
role = find_role_by_pin("1234567")  # "operator"

# Обновить PIN
update_pin("operator", "new_pin")
```

### Пример: сегментация

```python
from services.db import insert_seg_masks_batch, list_seg_masks

# Batch insert
n = insert_seg_masks_batch([
    {
        "id": "mask-1",
        "source_video": "archive/video.mp4",
        "time_sec": 12.5,
        "class_name": "ant_colony",
        "polygon_norm": [[0.1, 0.2], [0.3, 0.2], [0.2, 0.4]]
    }
])

# Получить маски
masks = list_seg_masks(
    source_video="video.mp4",
    time_from=10.0,
    time_to=20.0,
    track_id="track-123"
)
```

## WAL Mode

### Преимущества

| Параметр | Обычный | WAL |
|----------|---------|-----|
| Read during write | ❌ Блокируется | ✅ Разрешено |
| Write during read | ❌ Блокируется | ✅ Разрешено |
| Performance | Средняя | Высокая |
| Concurrency | Низкая | Высокая |

### Auto-checkpoint

```
P1-11: WAL checkpoint каждые 1000 страниц (~8 MB)
PRAGMA wal_autocheckpoint=1000
```

Explicit checkpoint через `checkpoint_wal(conn)` (PASSIVE mode).

## Оптимизация

### Индексы

Критические индексы для производительности:
- `detections(source_video, time_sec)` — основной query pattern
- `detections(class_name)` — фильтрация по классу
- `detections(created_at DESC)` — сортировка по дате
- `seg_masks(source_video, time_sec)` — маски по видео
- `network_targets(created_at DESC)` — цели по дате
- `active_learning_samples(status, created_at DESC)` — образцы по статусу

### Batch operations

```python
# Batch insert сегментов (быстрее по одному)
n = insert_seg_masks_batch(rows)  # rows: list[dict]

# Batch update через SQL
conn.executemany("INSERT INTO ...", data)
```

## Crops

**Путь:** `BASE_DIR/archive/crops/{detection_id}.jpg`

```python
from services.db import save_crop_jpeg

crop_path = save_crop_jpeg(
    detection_id="det-123",
    jpeg_bytes=frame_data,
    bbox={"x": 0.1, "y": 0.2, "w": 0.05, "h": 0.05}
)
# Returns: "crops/det-123.jpg" или None
```

## Troubleshooting

### Проблема: Database locked

```
SQLite database is locked
Solution:
1. Проверьте WAL mode: PRAGMA journal_mode;
2. Используйте _write_lock для WRITE-операций
3. Закройте другие подключения
4. Проверьте: PRAGMA busy_timeout=5000
```

### Проблема: Schema mismatch

```
Schema mismatch detected
Solution:
1. Перезапустите приложение (init_db() вызывается автоматически)
2. Проверьте: PRAGMA table_info(detections);
3. Проверьте версию: SELECT value FROM settings WHERE key = 'schema_version';
```

## Версия

- **Приложение:** v3.2.0
