# Схема базы данных (SQLite)

База: `muravei.db` в корне репозитория. Создаётся/мигрируется в [backend/services/db.py](../backend/services/db.py) (`init_db()`). Все таблицы — `CREATE TABLE IF NOT EXISTS`, миграции — через `PRAGMA table_info` + `ALTER TABLE`.

## Таблицы

### `pins` — PIN-коды ролей
| Столбец | Тип | Описание |
|---------|-----|----------|
| `role` | TEXT PK | `operator` / `engineer` / `master` |
| `pin_sha256` | TEXT | хэш PIN |
| `pin_b64` | TEXT | солёный хэш для проверки |
| `updated_at` | REAL | epoch |

### `settings` — key/value хранилище
| Столбец | Тип | Описание |
|---------|-----|----------|
| `key` | TEXT PK | имя настройки |
| `value` | TEXT | значение (строка; bool как `"0"`/`"1"`) |

Используется: `jwt_secret`, SAHI-настройки (`use_sahi_default`, `sahi_slice_*`, `sahi_overlap_ratio`), валидатор (`validator_enabled`, `validator_min_bbox_area`, `validator_max_bbox_area`, `validator_min_confidence`). См. [CONFIGURATION.md](CONFIGURATION.md).

### `lockouts` — защита от перебора PIN
| Столбец | Тип | Описание |
|---------|-----|----------|
| `client_key` | TEXT PK | идентификатор клиента |
| `fail_count` | INTEGER | счётчик неудач |
| `locked_until` | REAL | epoch до разблокировки |

### `detections` — детекции
| Столбец | Тип | Описание |
|---------|-----|----------|
| `id` | TEXT PK | UUID / `trk-N` |
| `created_at` | REAL | epoch |
| `source_video` | TEXT | путь ролика (scoped-фильтр по нему) |
| `time_sec` | REAL | время в ролике |
| `frame_idx` | INTEGER | индекс кадра |
| `class_id` | INTEGER | ID класса из каталога |
| `class_name` | TEXT | snake_case имя |
| `confidence` | REAL | 0..1 |
| `bbox_x`,`bbox_y`,`bbox_w`,`bbox_h` | REAL | нормализованный bbox (x,y — левый-верх, w,h) |
| `crop_path` | TEXT | путь кропа |
| `is_edited` | INTEGER | 0/1 — операторская правка |
| `edited_by` / `edited_at` | TEXT/REAL | кто/когда |
| `user_notes` | TEXT | заметки |
| `is_deleted` | INTEGER | 0/1 — soft-delete |
| `origin` | TEXT | `auto` / `batch_scan` |
| `ai_class_name` | TEXT | (миграция) предложение Ollama |

Миграции: `ai_class_name`, `gps_lat`, `gps_lon`, `gps_alt` добавляются `ALTER TABLE` при отсутствии.
Индексы: `idx_det_source_time(source_video, time_sec)`, `idx_det_class(class_name)`, `idx_det_notes(user_notes)`.

### `network_config` — конфиг сети (одна строка, `id=1`)
| Столбец | Тип | Описание |
|---------|-----|----------|
| `id` | INTEGER PK | всегда 1 |
| `mode` | TEXT | `off` / `server` / `client` |
| `server_ip` | TEXT | по умолчанию `127.0.0.1` |
| `port` | INTEGER | по умолчанию `8000` |
| `base_name` | TEXT | по умолчанию `База-1` |
| `updated_at` | REAL | epoch |

### `network_bases` — известные базы
| Столбец | Тип | Описание |
|---------|-----|----------|
| `id` | TEXT PK | |
| `base_name` | TEXT | |
| `ip` | TEXT | |
| `last_seen` | REAL | epoch |
| `status` | TEXT | `online` / `offline` |

### `network_targets` — цели между базами
| Столбец | Тип | Описание |
|---------|-----|----------|
| `id` | TEXT PK | |
| `created_at` | REAL | epoch |
| `direction` | TEXT | `incoming` / `outgoing` |
| `class_name` | TEXT | |
| `confidence` | REAL | |
| `gps_lat` / `gps_lon` | REAL | (миграция) |
| `crop_path` | TEXT | |
| `source_base` | TEXT | |
| `source_video` | TEXT | (миграция) — ролик-источник |
| `notes` | TEXT | |
| `expires_at` | REAL | TTL 24ч |

Индекс: `idx_net_targets_created(created_at DESC)`.

### `network_messages` — текстовые сообщения
| Столбец | Тип | Описание |
|---------|-----|----------|
| `id` | TEXT PK | |
| `created_at` | REAL | epoch |
| `direction` | TEXT | |
| `sender` | TEXT | |
| `body` | TEXT | |

Индекс: `idx_net_messages_created(created_at DESC)`.

### `class_overrides` — переопределения классов каталога
| Столбец | Тип | Описание |
|---------|-----|----------|
| `class_id` | INTEGER PK | ID класса |
| `name_ru` | TEXT | русское имя |
| `aliases` | TEXT | JSON-массив алиасов |
| `enabled` | INTEGER | 0/1 |
| `in_prompt` | INTEGER | 0/1 — в YOLOE prompt |
| `confidence_threshold` | REAL | nullable — порог для класса |
| `updated_at` | REAL | epoch |

### `flight_tracks` — телеметрия полёта
| Столбец | Тип | Описание |
|---------|-----|----------|
| `id` | TEXT PK | |
| `video_path` | TEXT UNIQUE | ролик |
| `track_data` | TEXT | JSON-массив точек |
| `source_file` | TEXT | SRT/CSV-источник |
| `created_at` | REAL | epoch |

Индекс: `idx_flight_tracks_video(video_path)`.

### `active_learning_samples` — очередь Active Learning
| Столбец | Тип | Описание |
|---------|-----|----------|
| `id` | TEXT PK | |
| `detection_id` | TEXT | |
| `source_video` | TEXT | |
| `time_sec` | REAL | |
| `feedback_type` | TEXT | тип отзыва |
| `proposed_class` | TEXT | предложенный класс |
| `status` | TEXT | `pending` / `accepted` / `rejected` |
| `created_at` / `updated_at` | REAL | epoch |

`UNIQUE(detection_id, feedback_type)`. Индекс: `idx_active_learning_status(status, created_at DESC)`.

## Миграции

`init_db()` после создания таблиц проверяет `PRAGMA table_info` и добивает недостающие столбцы через `ALTER TABLE`:
- `detections`: `ai_class_name`, `gps_lat`, `gps_lon`, `gps_alt`
- `network_targets`: `source_video`

Обновление схемы — только аддитивное; явных drop-миграций нет.
