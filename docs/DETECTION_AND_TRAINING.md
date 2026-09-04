# Детекция и обучение

## Веса

| Файл | Назначение |
|------|------------|
| `assets/models/yolo26n-ft.pt` | активный finetune (приоритет загрузки) |
| `assets/models/yolo26n.pt` / `best.pt` | nano / alias |
| `assets/models/yolo26n-seg.pt` / `yolo26s-seg.pt` | archive-only сегментация (не train, не `/ws/detect`) |
| `runs/.../yoloe-26s-seg.pt` | open-vocab YOLOE (нужен CLIP) |

Правила: только detect для train; `nc` 12 или 238 при импорте.

Переключение вручную: `YoloEngine.force_load(path)`.

## Классы

`military_classes.yaml` — 238 имён (танки, пехота, оружие, укрепления, litter, LBS-признаки, …).

UI словарь: панель SYSTEM → ClassDictionary. Soft floors / scene filters — в `yolo_engine.py` и `classes.py`.

## Инференс

1. Primary model predict (ft или YOLOE).  
2. Если пусто и primary не COCO-nano — fallback `yolo26n.pt`.  
3. Tracker IoU + ego LK.  
4. Ответ: objects, track_id, motion, ms, kind, nms_mode.

Конф UI по умолчанию ~0.20 (store).

## Быстрое обучение (UI)

UpdatePanel → кропы из SQLite → Ultralytics detect train → promote `yolo26n-ft.pt`.

Параметры по умолчанию (8 ГБ VRAM / RTX 5060): **imgsz=640**, **batch=4** (слайдеры до 1024 / 8 с предупреждением OOM). Только detect: `yolo26n.pt` / `yolo26n-ft.pt`, не YOLOE-seg.

**Resume:** `GET /api/train/checkpoints` показывает `last.pt` / `best.pt` / `epoch*.pt`. Кнопка «Продолжить обучение» шлёт `resume_from=last.pt` (`model.train(resume=True)`). Перед стартом — `torch.cuda.empty_cache()`. Нет чекпоинта → 404, обучение не стартует.

## Offline / backup finetune

Скрипт `backend/scripts/systematize_backup_finetune.py`:

- triage папок `.backup/.../downloaded` (Ollama vision / heuristics);
- выборка с nc=238, down-sample авиа/флот;
- `--train-only` на `cache/backup_finetune_ds`;
- CUDA с ретраями batch и `empty_cache`.

Smoke после promote:

```powershell
.\muravei_env\Scripts\python.exe backend\scripts\smoke_lbs_ft.py
```

Лог: `logs/smoke_lbs_ft.json`.

## CUDA

Проверка:

```powershell
.\muravei_env\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"
```

Ожидается `torch.*+cu128` и `True` на NVIDIA. Сборка `+cpu` даёт `cuda False` даже при живой RTX.

Установка (машина сборки):

```powershell
.\muravei_env\Scripts\pip.exe install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu128
.\muravei_env\Scripts\pip.exe install --no-cache-dir nvidia-ml-py
```

`pynvml` deprecated → в requirements указан `nvidia-ml-py`.

## LBS / мелкие объекты

Исторически: YOLOE + LBS prompts для окопов/проволоки; ft на 238 закрывает бронетехнику/грузовики лучше на размеченных доменах. Для редких классов 75–237 нужен autolabel (roadmap P1).
