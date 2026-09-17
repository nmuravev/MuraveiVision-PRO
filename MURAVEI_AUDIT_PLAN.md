# План исправлений ML-системы MuraveiVision-PRO

**Дата аудита:** 2026-09-18  
**Версия проекта:** B4 rev3  
**Статус:** 🟡 ТРЕБУЕТСЯ ВНИМАНИЕ  

---

## Executive Summary

| Метрика | Значение |
|---------|----------|
| Критических проблем (подтверждено) | 7 |
| Предупреждений | 12 |
| Новых выявленных проблем | 5 |
| Общее время на исправление P0+P1 | ~40 часов |
| Рекомендуемый срок реализации | 2-3 недели |

> **Примечание:** Проблемы C5 (SAM3 propagation) и C7 (VideoCapture leak) из исходного аудита **ОПРОВЕРГНУТЫ** — реализация существует в коде.

---

## 🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ (подтверждённые кодом)

### C1: Hardcoded COCO DROP list
- **Файл:** `yolo_engine.py:67-133`
- **Проблема:** Список из 78 исключаемых классов жёстко закодирован в `_COCO_DROP`
- **Риск:** При добавлении новых military-классов требуется правка кода
- **Конфликт:** Классы `plastic bottle` (70), `metal can` (71) могут конфликтовать с COCO `bottle` (84)

### C2: Нет graceful degradation при OOM
- **Файл:** `yolo_engine.py:548-560`
- **Проблема:** `_degraded=True` устанавливается, но нет retry-логики с `torch.cuda.empty_cache()`
- **Факт:** `torch.cuda.empty_cache()` вызывается только при unload (строка 339)

### C3: DirectML fallback не сохраняет state
- **Файл:** `yolo_engine.py:541-554`
- **Проблема:** При переключении DirectML→CPU модель не сохраняется, нужен рестарт
- **Факт:** Логика выбора бэкенда не кэширует состояние модели

### C4: Нет mutual exclusion с YOLO-detect
- **Файл:** `segmentation_engine.py`, `sam3_engine.py:125-131`
- **Проблема:** `sam3_engine.py` выгружает YOLO-seg, но `segmentation_engine.py` не выгружает YOLO-detect
- **Риск:** Обе модели могут занимать VRAM одновременно

### C6: Ollama timeout без rate limiting
- **Файл:** `ollama_proxy.py:581`, строка 32
- **Проблема:** `GENERATE_TIMEOUT = 60.0` по умолчанию, нет rate limiting на уровне API
- **Риск:** При зависшем Ollama backend блокируется

### C8: Нет progress persistence в batch segmentation
- **Файл:** `batch_segmentation.py:22-39`
- **Проблема:** `_state["results"]` хранится в памяти, при крахе прогресс теряется
- **Риск:** Нет SQLite checkpoint для resume

### C9: DepthAnything3 API не публичная
- **Файл:** `da3_pipeline.py:23`
- **Проблема:** `from depth_anything_3.api import DepthAnything3` может сломаться
- **Факт:** Есть try/except fallback (строки 22-25), но версия не зафиксирована

### C10: MODEL_NC=12 hardcoded
- **Файл:** `classes.py:14`, строка 419
- **Проблема:** Validation принимает только 12 или 238, но 12 не покрывает полный словарь
- **Факт:** `validate_model_nc(nc)` проверяет `nc not in (12, 238)`

---

## ⚠️ ПРЕДУПРЕЖДЕНИЯ (дополнительные к аудиту)

### W-New1: Prompt injection risk
- **Файл:** `api/ai.py:139-146`
- **Проблема:** `body.prompt` конкатенируется с `_VISION_PROMPT_PREFIX` без экранирования

### W-New2: Нет GPU memory monitoring
- **Проблема:** Ни один сервис не вызывает `torch.cuda.mem_get_info()` для мониторинга VRAM

### W-New3: Silent exceptions (BLE001)
- **Проблема:** 50+ случаев `except Exception: # noqa: BLE001` без логирования

### W-New4: Alias conflicts
- **Файл:** `classes.py:317-344`
- **Проблема:** `_LABEL_ALIASES` содержит 40+ маппингов, которые могут конфликтовать
- **Пример:** `"car": "military truck"` может ошибочно мапить гражданские автомобили

### W-New5: Нет cache на canonical_label()
- **Файл:** `classes.py:347-353`
- **Проблема:** Функция вызывается на каждый detection без кэширования

---

## 📋 ПЛАН ИСПРАВЛЕНИЙ (приоритизированный)

### P0 — Критические (неделя 1)

| № | Задача | Файлы | Оценка | Статус |
|---|--------|-------|--------|--------|
| 1 | Вынести `_COCO_DROP` в `military_classes.yaml` как `excluded_classes` | `yolo_engine.py`, `military_classes.yaml` | 4ч | ⏳ |
| 2 | Добавить `torch.cuda.empty_cache()` + retry при OOM | `yolo_engine.py` | 3ч | ⏳ |
| 3 | Добавить timeout=30 на Ollama generate() + rate limiting | `ollama_proxy.py`, `api/ai.py` | 2ч | ⏳ |
| 4 | Реализовать mutual exclusion YOLO-detect ↔ YOLO-seg | `yolo_engine.py`, `segmentation_engine.py` | 6ч | ⏳ |
| 5 | Добавить LRU cache на `canonical_label()` | `classes.py` | 2ч | ⏳ |

**Итого P0:** 17 часов

---

### P1 — Высокие (неделя 2)

| № | Задача | Файлы | Оценка | Статус |
|---|--------|-------|--------|--------|
| 6 | Добавить SQLite checkpoint для batch segmentation | `batch_segmentation.py`, `db.py` | 8ч | ⏳ |
| 7 | Pin `depth_anything_3` version в requirements.txt | `requirements.txt` | 1ч | ⏳ |
| 8 | Добавить GPU memory monitoring (Prometheus gauge) | Все сервисы | 8ч | ⏳ |
| 9 | Экранирование prompt в `/api/ai/analyze` | `api/ai.py` | 2ч | ⏳ |
| 10 | Вынести `_LABEL_ALIASES` в YAML с приоритетами | `classes.py`, `military_classes.yaml` | 4ч | ⏳ |

**Итого P1:** 23 часа

---

### P2 — Средние (неделя 3)

| № | Задача | Файлы | Оценка | Статус |
|---|--------|-------|--------|--------|
| 11 | Конфигурировать NMS/overlap через config.py | `yolo_engine.py`, `config.py` | 3ч | ⏳ |
| 12 | Добавить adaptive threshold для diff (Otsu's method) | `change_detection.py` | 4ч | ⏳ |
| 13 | GPS tolerance через config (aerial vs ground) | `change_detection.py`, `config.py` | 2ч | ⏳ |
| 14 | Добавить structured logging (JSON format) | Все сервисы | 8ч | ⏳ |
| 15 | Unit test для alias mapping edge cases | `tests/test_classes.py` | 4ч | ⏳ |

**Итого P2:** 21 час

---

### P3 — Долгосрочные (спринт 4+)

| № | Задача | Оценка | Статус |
|---|--------|--------|--------|
| 16 | Resource monitoring dashboard (Grafana + Prometheus) | 16ч | 📋 Backlog |
| 17 | Integration tests для всех 8 систем | 24ч | 📋 Backlog |
| 18 | Migration path для ultralytics API breaking changes | 12ч | 📋 Backlog |
| 19 | Batch size control + memory limit для batch segmentation | 6ч | 📋 Backlog |
| 20 | VRAM monitoring с adaptive step для DA3 | 4ч | 📋 Backlog |

**Итого P3:** 62 часа

---

## ✅ VERIFICATION STEPS

### Smoke Tests (после каждого этапа)

```bash
# 1. Проверка COCO DROP после миграции в YAML
python -c "from services.classes import get_class_catalog; c = get_class_catalog(); print(f'{len(c)} classes')"

# 2. Проверка Ollama timeout
curl -X POST http://localhost:8000/api/ai/analyze \
  -H "Content-Type: application/json" \
  -d '{"image_crop": "base64...", "prompt": "test", "timeout_sec": 30}'

# 3. Проверка GPU memory monitoring
python -c "import torch; free, total = torch.cuda.mem_get_info(); print(f'Free: {free/1e9:.2f}GB, Total: {total/1e9:.2f}GB')"

# 4. Проверка canonical_label cache
python -c "
from services.classes import canonical_label
import time
start = time.time()
[canonical_label('tank') for _ in range(1000)]
print(f'1000 calls: {time.time()-start:.3f}s')
"

# 5. Проверка SAM3 propagate (уже реализовано)
python -c "from services.sam3_propagate import status; print(status())"

# 6. Проверка VideoCapture leak (уже исправлено)
python -c "from services.change_detection import extract_video_frame; print('OK')"

# 7. Проверка mutual exclusion YOLO-detect ↔ YOLO-seg
python -c "
from services.yolo_engine import get_yolo_engine
from services.segmentation_engine import get_seg_engine
yolo = get_yolo_engine()
seg = get_seg_engine()
print(f'YOLO device: {yolo.device}, Seg device: {seg.device}')
"
```

### Integration Tests (после P1)

```bash
# Запуск интеграционных тестов
pytest tests/integration/test_yolo_oom.py -v
pytest tests/integration/test_ollama_timeout.py -v
pytest tests/integration/test_batch_seg_checkpoint.py -v
pytest tests/integration/test_gpu_monitoring.py -v
```

---

## 📊 METRICS & MONITORING

### Ключевые метрики для отслеживания

| Метрика | Текущее | Целевое | Инструмент |
|---------|---------|---------|------------|
| Покрытие тестами | ~40% | ≥75% | pytest-cov |
| Дублирование кода | Высокое | <10% | pylint-duplicate |
| Время ответа API (p95) | ? | <500ms | Prometheus |
| VRAM usage (max) | ? | <85% | nvidia-smi + exporter |
| OOM incidents | ? | 0 | Grafana alert |
| Prompt injection attempts | 0 | 0 | Structured log |

### Dashboard (Grafana)

**Панели:**
1. GPU Memory Usage (per service)
2. Request Latency (p50, p95, p99)
3. Error Rate (by endpoint)
4. Queue Depth (YOLO async queue)
5. Model Load/Unload Events
6. OLLAMA Timeout Events

---

## 📁 FILE INVENTORY (для изменений)

| Система | API File | Service File | Изменения |
|---------|----------|--------------|-----------|
| YOLO26 Detect | `backend/api/detect.py` | `backend/services/yolo_engine.py` | P0-1, P0-2, P2-11 |
| YOLO26 Seg | `backend/api/seg.py` | `backend/services/segmentation_engine.py` | P0-4 |
| SAM3 | `backend/api/seg.py` | `backend/services/sam3_engine.py` | — |
| SAM3 Propagate | `backend/api/seg.py` | `backend/services/sam3_propagate.py` | ✅ Уже реализовано |
| Ollama VLM | `backend/api/ai.py` | `backend/services/ollama_proxy.py` | P0-3, P1-9 |
| Change Detection | `backend/api/change_detection.py` | `backend/services/change_detection.py` | P2-12, P2-13 |
| Batch Seg | `backend/api/seg.py` | `backend/services/batch_segmentation.py` | P1-6 |
| DA3 | — | `backend/services/da3_pipeline.py` | P1-7, P3-20 |
| Classes | `backend/api/classes_api.py` | `backend/services/classes.py` | P0-5, P1-10, P2-15 |
| Config | — | `backend/config.py` | P2-11, P2-13 |
| DB | — | `backend/db.py` | P1-6 |
| Requirements | — | `requirements.txt` | P1-7 |
| Classes YAML | — | `assets/military_classes.yaml` | P0-1, P1-10 |

---

## 🎯 RISK MATRIX

| Риск | Вероятность | Impact | Митигация |
|------|-------------|--------|-----------|
| Breaking changes ultralytics API | Средняя | Высокий | P3-18: Migration layer |
| depth_anything_3 удалит API | Низкая | Высокий | P1-7: Pin version + fork |
| VRAM leak на продакшене | Высокая | Критический | P0-2, P1-8: Monitoring + auto-restart |
| Prompt injection атака | Средняя | Высокий | P1-9: Input sanitization |
| Alias conflict ложные срабатывания | Высокая | Средний | P1-10, P2-15: YAML priorities + tests |

---

## 📅 TIMELINE

```
Неделя 1 (P0):
├── День 1-2: Задачи 1, 2 (COCO DROP + OOM)
├── День 3: Задача 3 (Ollama timeout)
├── День 4-5: Задача 4 (Mutual exclusion)
└── День 5: Задача 5 (LRU cache) + smoke tests

Неделя 2 (P1):
├── День 1-3: Задача 6 (SQLite checkpoint)
├── День 3: Задача 7 (Pin DA3)
├── День 4-5: Задача 8 (GPU monitoring)
└── День 5: Задачи 9, 10 (Prompt + Aliases) + integration tests

Неделя 3 (P2):
├── День 1-2: Задачи 11, 12, 13 (Config + Otsu + GPS)
├── День 3-4: Задача 14 (Structured logging)
└── День 5: Задача 15 (Unit tests) + final verification

Спринт 4+ (P3):
└── По приоритету: Dashboard, Integration tests, Migration path
```

---

## 📝 ЗАКЛЮЧЕНИЕ

**Текущий статус:** 🟡 ТРЕБУЕТСЯ ВНИМАНИЕ  
**Критических проблем:** 7 (из 10 в исходном аудите, 3 опровергнуты)  
**Общий объём работ:** ~83 часа (P0+P1+P2+P3)  
**Минимальный план (P0+P1):** ~40 часов за 2 недели  

**Рекомендации:**
1. Начать с P0-1 (COCO DROP) — наименьший риск, высокая ценность
2. Параллельно реализовать P0-3 (Ollama timeout) — защита от зависаний
3. После P0 обязательно запустить smoke tests (раздел Verification)
4. P1-8 (GPU monitoring) критичен для стабильности на продакшене
5. Не забывать про документацию изменений в `CHANGELOG.md`

---

*Документ сгенерирован автоматически по результатам независимого аудита кода*  
*Для вопросов и уточнений обращайтесь к команде ML Infrastructure*
