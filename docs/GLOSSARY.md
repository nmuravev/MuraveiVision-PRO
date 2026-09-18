# Глоссарий терминов MuraveiVision PRO v3.2.0

## Как пользоваться

Каждый термин содержит:
- **Определение** — что это такое
- **Контекст** — для какой роли (Operator/Engineer/Developer)
- **См.** — ссылки на связанные документы

---

## A

### AI Analyst
**Определение:** Модуль анализа с использованием Ollama для обработки кадров и кропов, правила и тревоги.
**Контекст:** Operator
**См.:** [AI Analysis](01-OPERATOR/AI_ANALYSIS.md)

### Air-Gap
**Определение:** Режим работы без подключения к интернету. Все зависимости должны быть предварительно загружены.
**Контекст:** Engineer
**См.:** [Security & Air-Gap](06-SECURITY/AIR_GAP.md)

### AliceVision (AV)
**Определение:** Open-source pipeline для 3D реконструкции (MVS Dense, Mesh). Демонтирован до опционального режима.
**Контекст:** Engineer, Developer
**См.:** [3D Reconstruction](04-FEATURES/RECON_3D.md)

### Batch Change Detection
**Определение:** Сравнение двух архивных роликов по сохранённым детекциям (было/стало). GPS-matching ± time_window_sec.
**Контекст:** Operator
**См.:** [Batch Operations](04-FEATURES/BATCH_OPERATIONS.md)

### Batch Scan
**Определение:** Пакетное сканирование видео по детекциям YOLO. Запускается по ролику или I–O сегменту.
**Контекст:** Operator
**См.:** [Batch Scan](01-OPERATOR/BATCH_SCAN.md)

### Batch Segmentation
**Определение:** Пакетная сегментация по ролику. Один job за раз (409 если running).
**Контекст:** Operator
**См.:** [Segmentation](01-OPERATOR/SEGMENTATION.md)

---

## C

### COLMAP
**Определение:** Structure-from-Motion библиотека для создания sparse point cloud из фотографий. Используется в 3D реконструкции.
**Контекст:** Engineer, Developer
**См.:** [3D Reconstruction](04-FEATURES/RECON_3D.md)

### Commit
**Определение:** Фиксация кадра с детекциями. Кропы попадают в BattleGallery.
**Контекст:** Operator
**См.:** [Detection Workflow](01-OPERATOR/DETECTION_WORKFLOW.md)

### Configuration Keys
**Определение:** Параметры в SQLite (SAHI, Validator, Network). Изменяются без перезапуска.
**Контекст:** Engineer
**См.:** [Configuration](02-ENGINEER/CONFIGURATION.md)

---

## D

### DA3 (Depth Anything 3)
**Определение:** Модели плотной реконструкции (base/large/metric/giant). Sidecar-only, soft-fail на <8 COLMAP views.
**Контекст:** Engineer, Developer
**См.:** [3D Reconstruction](04-FEATURES/RECON_3D.md)

### Detection
**Определение:** Обнаружение объектов YOLO. Может быть в реальном времени (WS) или пакетно (Batch Scan).
**Контекст:** Operator
**См.:** [Detection](04-FEATURES/DETECTION.md)

### Detector
**Определение:** Модуль детекции (yolo_engine.py). Поддерживает YOLO26n-ft, SAHI, HUD Exclusion.
**Контекст:** Developer
**См.:** [Architecture](03-DEVELOPER/ARCHITECTURE.md)

### DirectML
**Определение:** AMD GPU acceleration на Windows. Альтернатива CUDA.
**Контекст:** Engineer
**См.:** [Hardware](02-ENGINEER/HARDWARE.md)

---

## E

### Engineer PIN
**Определение:** PIN `0000000` (по умолчанию). Требуется для загрузки моделей, импорта с USB, настроек сети.
**Контекст:** Engineer
**См.:** [Authentication](06-SECURITY/AUTH.md)

---

## F

### Flight3D
**Определение:** 3D viewer для sparse/dense/mesh/splat артефактов. Pick → sparse fallback.
**Контекст:** Operator
**См.:** [3D Reconstruction](04-FEATURES/RECON_3D.md)

### Filmstrip
**Определение:** Миниатюры таймлайна для быстрого навигирования по видео.
**Контекст:** Operator
**См.:** [Media Workflow](01-OPERATOR/MEDIA_WORKFLOW.md)

### FullKit
**Определение:** Полный portable package (18 GB warn / 22 GB reject). Включает DA3 sidecar.
**Контекст:** Engineer
**См.:** [Hardware](02-ENGINEER/HARDWARE.md)

---

## G

### GSplat
**Определение:** Gaussian Splatting для 3D визуализации. Требует MSVC build на Windows.
**Контекст:** Engineer, Developer
**См.:** [3D Reconstruction](04-FEATURES/RECON_3D.md)

### GPS Sidecar
**Определение:** Файл GPS-меток рядом с видео (.SRT, .CSV DJI format). Координаты пишутся на детекции.
**Контекст:** Operator
**См.:** [Media Workflow](01-OPERATOR/MEDIA_WORKFLOW.md)

---

## H

### HUD Exclusion
**Определение:** Автоматическое размытие/каппинг объектов (детекции, CD, recon) на overlay.
**Контекст:** Operator
**См.:** [Detection](04-FEATURES/DETECTION.md)

---

## I

### Inspector
**Определение:** Панель редактирования детекций: класс, bbox, crop, Ollama предложение.
**Контекст:** Operator
**См.:** [Detection Workflow](01-OPERATOR/DETECTION_WORKFLOW.md)

### In/Out Markers
**Определение:** Маркеры I/O для задания сегмента видео. `I`/`O` hotkeys. Используются для Batch Scan и 3D.
**Контекст:** Operator
**См.:** [Media Workflow](01-OPERATOR/MEDIA_WORKFLOW.md)

---

## J

### JWT (JSON Web Token)
**Определение:** Токен аутентификации. Генерируется после login с PIN. Хранится в localStorage.
**Контекст:** Engineer, Developer
**См.:** [Authentication](06-SECURITY/AUTH.md)

---

## L

### Live Stream
**Определение:** RTSP/UDP/HTTP поток в реальном времени. Режим Live в Viewer.
**Контекст:** Operator
**См.:** [Media Workflow](01-OPERATOR/MEDIA_WORKFLOW.md)

---

## M

### Mini Pack
**Определение:** Минимальный portable package (4.5 GB warn / 5 GB reject). Без DA3.
**Контекст:** Engineer
**См.:** [Hardware](02-ENGINEER/HARDWARE.md)

### Mosaic Layout
**Определение:** Система раскладок с Mosaic windows. Presets: Media, 4×Live, Quad.
**Контекст:** Operator
**См.:** [Overview](01-OPERATOR/OVERVIEW.md)

---

## N

### Network v3.3
**Определение:** Репликация между базами (N1-N6). WebSocket chat, REST worker, beacon UDP.
**Контекст:** Engineer
**См.:** [Network](04-FEATURES/NETWORK.md)

### N1-N6
**Определение:** Фазы Network v3.3:
- N1: `/ws/chat?token=` realtime chat
- N2: Chunked REST attachments (8 MB)
- N3: `detection:<id>` refs in chat
- N4: Recon package share
- N5: Opt-in LAN beacon UDP 8001
- N6: `dual_network_smoke.py` 12 cases
**Контекст:** Engineer
**См.:** [Network](04-FEATURES/NETWORK.md)

---

## O

### Ollama
**Определение:** Локальный LLM proxy для AI-анализа кадров и кропов. Discovery + proxy.
**Контекст:** Operator
**См.:** [AI Analysis](01-OPERATOR/AI_ANALYSIS.md)

### Operator PIN
**Определение:** PIN `1234567` (по умолчанию). Требуется для полевой работы.
**Контекст:** Operator
**См.:** [Authentication](06-SECURITY/AUTH.md)

---

## P

### Portable Build
**Определение:** Сборка автономного пакета (make_env_pack.ps1). Включает wheels, models, sidecars.
**Контекст:** Engineer
**См.:** [Portable](04-FEATURES/PORTABLE.md)

### Preset Hierarchy
**Определение:** Иерархия пресетов реконструкции: Sparse → Dense (DA3) → Mesh (AV) → Splat.
**Контекст:** Operator, Engineer
**См.:** [3D Reconstruction](04-FEATURES/RECON_3D.md)

---

## R

### Recon (Reconstruction)
**Определение:** 3D реконструкция: COLMAP sparse → DA3 dense → GSplat splat.
**Контекст:** Operator, Engineer
**См.:** [3D Reconstruction](04-FEATURES/RECON_3D.md)

### REST Worker Tick
**Определение:** Фоновый worker каждые ~15 с для синхронизации целей между базами.
**Контекст:** Engineer
**См.:** [Network](04-FEATURES/NETWORK.md)

---

## S

### SAHI (Slicing Aided Hyper Inference)
**Определение:** Нарезка кадра на части для поиска мелких объектов. Параметры: slice_height/width, overlap_ratio.
**Контекст:** Operator, Engineer
**См.:** [Detection](04-FEATURES/DETECTION.md)

### SAM3 (Segment Anything Model 3)
**Определение:** Интерактивная сегментация: точка, бокс, текст. Propagate ≤30 frames (chunked full-video).
**Контекст:** Operator
**См.:** [Segmentation](01-OPERATOR/SEGMENTATION.md)

### Session Trace
**Определение:** Логирование сессии (sessionStorage UUID). Page-lifetime singleton.
**Контекст:** Developer
**См.:** [AI Analysis](01-OPERATOR/AI_ANALYSIS.md)

### SQLite
**Определение:** Локальная БД (muravei.db). Settings, detections, seg_masks, batch_seg_jobs.
**Контекст:** Developer
**См.:** [Database](03-DEVELOPER/DATABASE.md)

### Sparse Point Cloud
**Определение:** Облако точек из COLMAP. Предшественник dense reconstruction.
**Контекст:** Operator, Engineer
**См.:** [3D Reconstruction](04-FEATURES/RECON_3D.md)

---

## T

### Timeline
**Определение:** Панель таймлайна с playhead, scrubbing, filmstrip. Sync mode: follow/lock.
**Контекст:** Operator
**См.:** [Media Workflow](01-OPERATOR/MEDIA_WORKFLOW.md)

---

## V

### Viewer
**Определение:** Панель просмотра видео/стрима. 4 viewers (viewer-1…viewer-4) в Mosaic layout.
**Контекст:** Operator
**См.:** [Overview](01-OPERATOR/OVERVIEW.md)

### VRAM
**Определение:** Видеопамять. Критичный ресурс: detect + seg не держатся одновременно на 8 GB.
**Контекст:** Engineer
**См.:** [Hardware](02-ENGINEER/HARDWARE.md)

---

## W

### WebSocket (WS)
**Определение:** Realtime communication. `/ws/detect/{viewer_id}` для детекции, `/ws/chat?token=` для чата.
**Контекст:** Developer, Engineer
**См.:** [Network](04-FEATURES/NETWORK.md)

### Whitelist
**Определение:** Разрешённые имена моделей (yolo26n-seg.pt, yolo26s-seg.pt). YOLOE-seg отклоняются.
**Контекст:** Engineer
**См.:** [Models](02-ENGINEER/MODELS.md)

---

## Y

### YOLO
**Определение:** You Only Look Once — семейство моделей детекции. YOLO26n-ft (default), ladder s/m/l-ft.
**Контекст:** Operator, Engineer, Developer
**См.:** [Detection](04-FEATURES/DETECTION.md)

### YOLO-seg
**Определение:** Отдельный пайплайн сегментации (не base для detect). Веса: yolo26n-seg.pt, yolo26s-seg.pt.
**Контекст:** Operator, Engineer
**См.:** [Segmentation](01-OPERATOR/SEGMENTATION.md)

---

## Завершение

Этот глоссарий будет расширяться по мере добавления новых фич. Все термины используются единообразно во всей документации.
