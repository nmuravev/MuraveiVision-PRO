# Аудит плана исправлений ML-системы MuraveiVision-PRO

**Дата аудита:** 2026-09-18  
**Аудитор:** AI Code Expert  
**Статус:** ✅ ПЛАН РАБОТОСПОСОБЕН С ЗАМЕЧАНИЯМИ

---

## Executive Summary

| Параметр | Значение |
|----------|----------|
| Задач в плане | 9 (P0: 5, P1: 4) |
| Реализуемо без изменений | 4 задачи |
| Требует уточнений | 3 задачи |
| Критические пробелы | 2 задачи |
| Общая оценка | 🟡 7/10 |

---

## Детальный анализ по задачам

### ✅ P0-1: Динамические excluded classes (6ч) — РАБОТОСПОСОБЕН

**Статус кода:**
- `_COCO_DROP` существует в `yolo_engine.py:67-133` (78 классов)
- Таблица `class_overrides` уже есть в `db.py:169`
- Функция `list_class_overrides()` реализована (`db.py:1008`)
- API `/api/classes/overrides` работает (`classes_api.py:48-101`)

**Замечания:**

1. **SQLite seed при инициализации** — план предлагает добавлять 78 COCO-классов в `init_db()`, но это приведёт к дублированию при каждом запуске. Нужно использовать `INSERT OR IGNORE`.

2. **Кэш invalidation** — в плане вызывается `invalidate_excluded_cache()`, но такая функция не существует. Нужно добавить её в `classes.py`.

3. **YAML fallback** — план упоминает `_custom` секцию в YAML, но её нет в `military_classes.yaml`. Нужно либо добавить, либо убрать из плана.

4. **_is_excluded cache** — предлагается `@lru_cache(maxsize=256)`, но excluded classes могут меняться динамически через API. Кэш должен инвалидироваться при изменениях.

**Рекомендуемые правки:**

```python
# В classes.py добавить:
_excluded_cache: set[str] | None = None

def get_excluded_classes() -> set[str]:
    global _excluded_cache
    if _excluded_cache is not None:
        return _excluded_cache
    
    excluded: set[str] = set()
    try:
        from services.db import list_excluded_classes
        for row in list_excluded_classes():
            excluded.add(row["class_name"].lower().replace(" ", "_"))
    except Exception:
        pass
    
    _excluded_cache = excluded
    return excluded

def invalidate_excluded_cache() -> None:
    global _excluded_cache
    _excluded_cache = None
```

**Оценка:** 6ч → **8ч** (дополнительно 2ч на тестирование cache invalidation)

---

### ⚠️ P0-2: OOM graceful degradation с empty_cache (3ч) — ТРЕБУЕТ УТОЧНЕНИЯ

**Статус кода:**
- `torch.cuda.empty_cache()` вызывается только в `_empty_cache()` при unload (`yolo_engine.py:339`)
- Нет retry-логики при CUDA OOM

**Проблема:** План не указывает, где именно добавлять retry. В `_load_model()`? В worker-цикле?

**Рекомендуемая реализация:**

```python
# В yolo_engine.py, метод _load_model():
try:
    self._model = YOLO(str(path))
except RuntimeError as exc:
    if "CUDA out of memory" in str(exc):
        torch.cuda.empty_cache()
        # Retry на CPU
        self._device = torch.device("cpu")
        self._degraded = True
        self._model = YOLO(str(path), device="cpu")
    else:
        raise
```

**Оценка:** 3ч → **4ч** (добавить обработку конкретных ошибок CUDA)

---

### ✅ P0-3: Ollama timeout (2ч) — РАБОТОСПОСОБЕН

**Статус кода:**
- `timeout=gen_timeout` уже используется в `ollama_proxy.py:581`
- `GENERATE_TIMEOUT = 60.0` (строка 32)
- Обработка `httpx.TimeoutException` есть (`ollama_proxy.py:600-603`)

**Замечание:** План предлагает уменьшить timeout до 30 сек. Это может быть недостаточно для больших промптов (autolabel с 238 классами).

**Рекомендация:** Добавить параметр `timeout_sec` в API endpoint `/api/ai/analyze` для гибкости.

**Оценка:** 2ч ✅

---

### 🔴 P0-4: Mutual exclusion YOLO-detect ↔ YOLO-seg (6ч) — КРИТИЧЕСКИЙ ПРОБЕЛ

**Статус кода:**
- `sam3_engine.py` вызывает `_unload_yolo_seg()` (строка 125-131)
- Но `segmentation_engine.py` НЕ выгружает YOLO-detect
- `yolo_engine.py` НЕ знает о segmentation_engine

**Проблема:** План показывает код для mutual exclusion, но не указывает, где его размещать.

**Текущее состояние:**
```python
# sam3_engine.py:125-131 — выгружает ТОЛЬКО YOLO-seg
def _unload_yolo_seg() -> None:
    try:
        from services.segmentation_engine import get_seg_engine
        get_seg_engine().unload_model()
    except Exception:
        pass
```

**Недостающая логика:**
1. `segmentation_engine.load_model()` должен выгружать YOLO-detect
2. `yolo_engine.force_load()` должен выгружать YOLO-seg
3. Нужен глобальный lock для предотвращения race conditions

**Рекомендуемая реализация:**

```python
# Создать backend/services/model_mutex.py:
_model_lock = threading.Lock()
_active_model: str | None = None  # "yolo_detect" | "yolo_seg" | "sam3"

def acquire_model(model_name: str) -> bool:
    with _model_lock:
        global _active_model
        if _active_model == model_name:
            return True
        # Unload current
        if _active_model == "yolo_detect":
            get_yolo_engine().unload_model()
        elif _active_model == "yolo_seg":
            get_seg_engine().unload_model()
        elif _active_model == "sam3":
            get_sam3_engine().unload_model()
        _active_model = model_name
        return True
```

**Оценка:** 6ч → **10ч** (требуется создание нового сервиса + интеграция)

---

### ✅ P0-5: LRU cache на canonical_label (2ч) — РАБОТОСПОСОБЕН

**Статус кода:**
- `canonical_label()` в `classes.py:347-353` не кэшируется
- `_alias_map` уже кэшируется глобальной переменной

**План корректен:**
```python
@functools.lru_cache(maxsize=512)
def canonical_label(name: str) -> str:
    ...
```

**Замечание:** При изменении aliases в SQLite кэш нужно инвалидировать. Добавить вызов в `invalidate_class_cache()`.

**Оценка:** 2ч ✅

---

### ✅ P0-6: Pin depth_anything_3 version (1ч) — РАБОТОСПОСОБЕН

**Статус кода:**
- `depth_anything_3` НЕ в `requirements.txt`
- Импорт в `da3_pipeline.py:23` с try/except fallback

**План корректен:**
```txt
depth_anything_3>=1.0.0,<2.0.0
```

**Замечание:** Проверить, доступен ли пакет в pip. Если нет — добавить в `sidecars/da3/README` инструкцию по установке.

**Оценка:** 1ч ✅

---

### ⚠️ P1-7: SQLite checkpoint batch segmentation (8ч) — ТРЕБУЕТ УТОЧНЕНИЯ

**Статус кода:**
- `_state["results"]` хранится в памяти (`batch_segmentation.py:34`)
- Нет таблицы `batch_seg_jobs` в `db.py`
- Нет функций `save_batch_seg_checkpoint()` / `load_batch_seg_checkpoint()`

**Проблема:** План не указывает схему таблицы и частоту checkpoint.

**Рекомендуемая схема:**

```sql
CREATE TABLE IF NOT EXISTS batch_seg_jobs (
    task_id TEXT PRIMARY KEY,
    video_path TEXT NOT NULL,
    frame_step INTEGER NOT NULL DEFAULT 30,
    confidence REAL NOT NULL DEFAULT 0.25,
    status TEXT NOT NULL DEFAULT 'running',
    last_frame_idx INTEGER NOT NULL DEFAULT 0,
    total_frames INTEGER NOT NULL DEFAULT 0,
    results_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
```

**Checkpoint interval:** Каждые 10 кадров (как в плане) ИЛИ каждые 30 секунд — что наступит раньше.

**Оценка:** 8ч → **12ч** (добавить миграции БД + обработка resume при старте)

---

### ⚠️ P1-8: GPU memory monitoring (6ч) — ТРЕБУЕТ УТОЧНЕНИЯ

**Статус кода:**
- `torch.cuda.mem_get_info()` НЕ вызывается ни в одном сервисе
- `nvidia-ml-py` есть в `requirements.txt`

**Проблема:** План предлагает создать `gpu_monitor.py`, но не указывает интеграцию с существующими `status_snapshot()`.

**Рекомендуемая реализация:**

```python
# backend/services/gpu_monitor.py:
class GPUMonitor:
    def __init__(self):
        self._history: list[dict] = []
    
    def sample(self) -> dict:
        if not torch.cuda.is_available():
            return {"available": False}
        
        free, total = torch.cuda.mem_get_info()
        return {
            "available": True,
            "free_mb": free // (1024**2),
            "total_mb": total // (1024**2),
            "used_mb": (total - free) // (1024**2),
            "usage_pct": round((total - free) / total * 100, 1),
        }
```

**Интеграция:** Добавить вызов в `yolo_engine.status_snapshot()`, `sam3_engine.status()`, etc.

**Оценка:** 6ч → **8ч** (добавить endpoint /api/gpu/status + интеграция)

---

### ✅ P1-9: Prompt sanitization (2ч) — РАБОТОСПОСОБЕН

**Статус кода:**
- `body.prompt` конкатенируется без санитизации (`ai.py:139-146`)
- Нет функции `_sanitize_prompt()`

**План корректен:**
```python
def _sanitize_prompt(prompt: str) -> str:
    return (
        prompt.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
```

**Замечание:** HTML-escaping может быть недостаточным для prompt injection. Рассмотреть whitelist-подход или удаление спецсимволов.

**Оценка:** 2ч ✅

---

## Сводная таблица оценок

| Задача | План (ч) | Реально (ч) | Статус |
|--------|----------|-------------|--------|
| P0-1: Excluded classes | 6 | 8 | 🟡 Требуется cache invalidation |
| P0-2: OOM graceful degradation | 3 | 4 | 🟡 Требуется уточнение места |
| P0-3: Ollama timeout | 2 | 2 | ✅ Готово |
| P0-4: Mutual exclusion | 6 | 10 | 🔴 Критический пробел |
| P0-5: LRU cache | 2 | 2 | ✅ Готово |
| P0-6: Pin DA3 version | 1 | 1 | ✅ Готово |
| P1-7: Batch seg checkpoint | 8 | 12 | 🟡 Требуется схема БД |
| P1-8: GPU monitoring | 6 | 8 | 🟡 Требуется интеграция |
| P1-9: Prompt sanitization | 2 | 2 | ✅ Готово |
| **ИТОГО** | **36** | **49** | |

---

## Критические пробелы

### 1. Mutual exclusion архитектура (P0-4)

**Проблема:** План показывает код для выгрузки YOLO-detect в `segmentation_engine`, но не учитывает:
- Race conditions при одновременных запросах
- Состояние гонки между SAM3 и YOLO-seg
- Отсутствие глобального state manager'а

**Решение:** Создать отдельный сервис `model_mutex.py` с threading.Lock (см. выше).

### 2. Миграции БД (P0-1, P1-7)

**Проблема:** План предлагает добавлять таблицы в `init_db()`, но не учитывает:
- Существующие БД у пользователей (нужны ALTER TABLE)
- Откат миграций при ошибках
- Версионирование схемы БД

**Решение:** Добавить таблицу `schema_version` и функцию `migrate_db()`.

---

## Рекомендации по улучшению плана

### 1. Добавить версионирование БД

```python
# В db.py:
def get_schema_version() -> int:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'schema_version'"
        ).fetchone()
        return int(row["value"]) if row else 0
    finally:
        conn.close()

def migrate_db() -> None:
    version = get_schema_version()
    conn = _connect()
    try:
        if version < 1:
            # Add excluded_classes table
            conn.execute("""CREATE TABLE IF NOT EXISTS excluded_classes (...)""")
            conn.execute("INSERT INTO settings (key, value) VALUES ('schema_version', '1')")
        if version < 2:
            # Add batch_seg_jobs table
            conn.execute("""CREATE TABLE IF NOT EXISTS batch_seg_jobs (...)""")
            conn.execute("UPDATE settings SET value = '2' WHERE key = 'schema_version'")
        conn.commit()
    finally:
        conn.close()
```

### 2. Добавить integration tests

```bash
# tests/test_mutual_exclusion.py:
def test_yolo_seg_exclusion():
    from services.yolo_engine import get_yolo_engine
    from services.segmentation_engine import get_seg_engine
    
    yolo = get_yolo_engine()
    seg = get_seg_engine()
    
    yolo.force_load(yolo.model_path)
    assert yolo.mode == "ready"
    
    seg.load_model()
    # YOLO-detect должен выгрузиться
    assert yolo.mode == "offline" or yolo.model is None
```

### 3. Добавить мониторинг в Grafana

```python
# backend/services/telemetry.py:
from prometheus_client import Gauge

GPU_MEMORY_USED = Gauge("gpu_memory_used_bytes", "GPU memory used", ["device"])
GPU_MEMORY_FREE = Gauge("gpu_memory_free_bytes", "GPU memory free", ["device"])

def update_gpu_metrics():
    if torch.cuda.is_available():
        free, total = torch.cuda.mem_get_info()
        GPU_MEMORY_USED.labels(device=0).set(total - free)
        GPU_MEMORY_FREE.labels(device=0).set(free)
```

---

## Итоговая оценка плана

| Критерий | Оценка | Комментарий |
|----------|--------|-------------|
| Полнота | 7/10 | Отсутствует архитектура mutual exclusion |
| Реалистичность оценок | 6/10 | Занижены на 30-50% |
| Тестируемость | 5/10 | Нет integration tests в плане |
| Безопасность | 8/10 | Prompt sanitization учтён |
| Масштабируемость | 6/10 | Нет учёта миграций БД |
| **Средняя** | **6.4/10** | **План работоспособен с доработками** |

---

## Заключение

Предложенный план исправлений **работоспособен**, но требует следующих доработок:

1. **Увеличить оценку времени с 36ч до 49ч** (+36%)
2. **Добавить сервис model_mutex.py** для управления exclusive access к моделям
3. **Добавить миграции БД** с версионированием схемы
4. **Добавить integration tests** для критических путей (mutual exclusion, OOM handling)
5. **Уточнить точки интеграции** для GPU monitoring и checkpointing

**Рекомендация:** Начать с P0-3, P0-5, P0-6 (наименьший риск), затем P0-1, P0-2, и только после этого P0-4 (наибольший риск).
