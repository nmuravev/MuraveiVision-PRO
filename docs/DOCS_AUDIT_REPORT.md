# Audit: Documentation vs Project State

## Проверено: 19.09.2026

---

## ✅ СООТВЕТСТВУЕТ

### 1. Версия приложения
- **Документация:** v3.2.0
- **Реальность:** `3.2.0-78-g917af24` (git describe)
- **Статус:** ✅ ОК — базовая версия совпадает

### 2. Структура backend/
- **Документация:** api/, services/, models/, schemas/, utils/
- **Реальность:** 
  - api/ — 28 файлов (detect, auth, ai, network, seg, recon, train, export, geo, hud, live, map, rec, scan, ws_chat, classes_api, debug, events, export, models, network, queue, reports, support, system, active_learning, change_detection)
  - services/ — 75 файлов
  - config.py ✅
  - database.py → services/db.py ✅
- **Статус:** ✅ ОК — структура совпадает, документация обобщённая

### 3. База данных
- **Документация:** 8 таблиц (sessions, detections, segments, models, users, network_peers, chat_messages, session_trace)
- **Реальность:** services/db.py — pins, settings, lockouts, detections
- **Статус:** ⚠️ ЧАСТИЧНО — реальные таблицы отличаются (db.py хранит pins/settings/lockouts/detections, а не sessions/segments/users)

### 4. API Endpoints
- **Документация:** /api/detect, /api/segment, /api/ai, /api/batch, /api/network, /api/auth, /api/sessions
- **Реальность:** 28 API файлов с множеством endpoints
- **Статус:** ✅ ОК — документация показывает ключевые endpoints, не все

### 5. Модельный стек
- **Документация:** YOLOv8/v11, SAM3, DA3, Ollama
- **Реальность:** 
  - TACTICAL_WEIGHT_LADDER: yolo26l-ft, yolo26m-ft, yolo26s-ft, yolo26n-ft, yolo26n (YOLO26!)
  - sam3_engine.py ✅
  - da3_pipeline.py ✅
  - ollama_proxy.py ✅
- **Статус:** ⚠️ НЕСООТВЕТСТВИЕ — в реальности используются YOLO26 (yolo26l-ft и т.д.), а не YOLOv8/v11

### 6. GPU поддержка
- **Документация:** CUDA, DirectML, CPU
- **Реальность:** ENGINE_STATUS_CUDA, ENGINE_STATUS_DIRECTML, ENGINE_STATUS_CPU ✅
- **Статус:** ✅ ОК

### 7. Air-gap enforcement
- **Документация:** Описан air-gap режим
- **Реальность:** 
  - ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS=1 ✅
  - YOLO_AUTOINSTALL=0 ✅
  - site.USER_SITE=None ✅
  - ultralytics_airgap.py ✅
- **Статус:** ✅ ОК

### 8. Портативные киты
- **Документация:** mini, lite, fullkit
- **Реальность:** KIT file → mini|full; MURAVEI_BUILD_PROFILE env; read_kit()
- **Статус:** ⚠️ НЕСООТВЕТСТВИЕ — в реальности только mini/full (не lite)

---

## ❌ НЕСООТВЕТСТВИЯ

### 1. YOLO версии (КРИТИЧНО)
- **Документация:** YOLOv8n/s/m/l/x, YOLOv11n/s
- **Реальность:** `yolo26l-ft.pt`, `yolo26m-ft.pt`, `yolo26s-ft.pt`, `yolo26n-ft.pt`, `yolo26n.pt`
- **Файлы:** `backend/config.py` строка 14-18
- **Требуется:** Обновить все упоминания YOLOv8/v11 → YOLO26

### 2. Lite vs Fullkit
- **Документация:** mini, lite, fullkit профили
- **Реальность:** `read_kit()` возвращает только mini|full|dev
- **Файлы:** `backend/config.py` строка 57-67
- **Требуется:** Удалить "lite", добавить "full"

### 3. Структура БД
- **Документация:** 8 таблиц (sessions, detections, segments, models, users, network_peers, chat_messages, session_trace)
- **Реальность:** db.py хранит:
  - pins (operator, engineer, master)
  - settings (ключ-значение)
  - lockouts (блокировки)
  - detections (результаты обнаружения)
  - Нет таблиц: sessions, segments, users, network_peers, chat_messages, session_trace
- **Файлы:** `backend/services/db.py`
- **Требуется:** Полностью переписать раздел Database Schema

### 4. Базовые PIN-коды
- **Документация:** Не указаны
- **Реальность:** `DEFAULT_PINS = {"operator": "1234567", "engineer": "0000000", "master": "0987907"}`
- **Файлы:** `backend/services/db.py` строка 22-25
- **Требуется:** Добавить в раздел Security

### 5. API endpoints
- **Документация:** 20 endpoints (обобщённо)
- **Реальность:** 28 API файлов, ~100+ endpoints
- **Требуется:** Обновить API Reference (но это ок для high-level docs)

### 6. Services
- **Документация:** detection_service, segmentation_service, batch_service
- **Реальность:** 75 service файлов, включая:
  - ai_crops, autolabel, batch_change_detection, batch_scanner, batch_segmentation
  - catalog, change_detection, change_export
  - colmap_poses, da3_pipeline
  - geo_export, gsplat_msvc, hardware_detect, hud_exclusion
  - live_stream, map_tiles, network_recon_share, network_sync
  - ollama_discovery, ollama_proxy
  - recon_colmap, recon_scanner, recon_train
  - sahi_yolo_engine, sam3_engine, sam3_propagate
  - trainer, train_presets, ultralytics_airgap
  - yolo_directml и др.
- **Требуется:** Обновить Architecture раздел

---

## 📊 Сводка

| Категория | Статус | Кол-во несоответствий |
|-----------|--------|----------------------|
| **Версия** | ✅ ОК | 0 |
| **YOLO версии** | ❌ НЕСООТВЕТСТВИЕ | 1 (v8/v11 → 26) |
| **Профили китов** | ❌ НЕСООТВЕТСТВИЕ | 1 (lite → full) |
| **База данных** | ❌ НЕСООТВЕТСТВИЕ | 1 (schema полностью другая) |
| **PIN-коды** | ❌ НЕСООТВЕТСТВИЕ | 1 (не указаны) |
| **API** | ✅ ОК (обобщённо) | 0 |
| **Services** | ⚠️ ЧАСТИЧНО | 1 (упрощено) |
| **GPU/air-gap** | ✅ ОК | 0 |

**Итого:** 5 несоответствий, 1 частичное

---

## 🔧 План исправлений документации

### HIGH Priority (требуют исправления):

1. **YOLO версии:** YOLOv8/v11 → YOLO26 (yolo26n/s/m/l-ft)
   - Файлы: docs/01-OPERATOR/DETECTION.md, docs/04-FEATURES/DETECTION.md, docs/03-DEVELOPER/ARCHITECTURE.md
   
2. **Профили китов:** lite → full
   - Файлы: docs/02-ENGINEER/DEPLOYMENT.md, docs/04-FEATURES/PORTABLE.md, docs/06-SECURITY/AIR_GAP.md

3. **База данных:** Полностью переписать schema
   - Файлы: docs/05-REFERENCE/DATABASE_SCHEMA.md, docs/03-DEVELOPER/DATABASE.md

### MEDIUM Priority:

4. **PIN-коды:** Добавить в Security
   - Файлы: docs/06-SECURITY/AUTH.md, docs/06-SECURITY/SECURITY_AUDIT.md

5. **Services:** Обновить Architecture diagram
   - Файлы: docs/03-DEVELOPER/ARCHITECTURE.md

### LOW Priority:

6. **API:** Добавить больше endpoints (опционально)
   - Файлы: docs/05-REFERENCE/API_ENDPOINTS.md
