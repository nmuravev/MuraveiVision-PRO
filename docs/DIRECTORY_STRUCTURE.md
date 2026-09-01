# Структура директорий

Актуально для `MuraveiVision-PRO` (не `.backup`).

```
MuraveiVision-PRO/
├── README.md                      # краткий вход → docs/
├── docs/                          # вся проектная документация
├── package.json                   # Vite + npm scripts (backend/desktop/portable)
├── military_classes.yaml          # 238 классов
├── Запустить.bat                  # полевой старт Portable / локальный
├── start-backend.bat
├── muravei_env/                   # Python 3.12.10 (+ site-packages)
├── mobileclip2_b.ts               # опционально, для YOLOE CLIP
│
├── backend/
│   ├── main.py                    # FastAPI app, lifespan, static dist
│   ├── desktop_launcher.py        # pywebview + uvicorn
│   ├── requirements.txt
│   ├── api/                       # HTTP/WS роутеры
│   │   ├── auth.py
│   │   ├── media.py
│   │   ├── detect.py              # POST /api/detect + WS
│   │   ├── detections.py
│   │   ├── active_learning.py
│   │   ├── train.py
│   │   ├── ai.py
│   │   ├── live.py
│   │   ├── rec.py
│   │   ├── reports.py
│   │   ├── models.py
│   │   ├── system.py
│   │   ├── network.py
│   │   ├── classes_api.py
│   │   ├── geo.py
│   │   ├── scan.py
│   │   ├── recon.py
│   │   ├── queue.py
│   │   └── support.py
│   ├── services/                  # бизнес-логика
│   │   ├── yolo_engine.py
│   │   ├── trainer.py
│   │   ├── classes.py
│   │   ├── tracker.py
│   │   ├── motion.py
│   │   ├── similarity.py
│   │   ├── ollama_proxy.py
│   │   ├── live_stream.py
│   │   ├── recorder.py
│   │   ├── recon_scanner.py
│   │   ├── colmap_poses.py
│   │   ├── reporter.py
│   │   ├── model_validator.py
│   │   ├── db.py
│   │   ├── hardware.py
│   │   ├── network.py
│   │   ├── security.py
│   │   └── trash.py
│   └── scripts/                   # smoke / finetune / autolabel
│       ├── smoke_lbs_ft.py
│       ├── smoke_video_s3.py
│       ├── systematize_backup_finetune.py
│       ├── autolabel_train_lbs_video.py
│       ├── smoke_phase3.py
│       └── smoke_phase4.py
│
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── components/
│   │   ├── ComponentRegistry.tsx
│   │   ├── TopBar.tsx
│   │   ├── SplashScreen.tsx
│   │   └── panels/
│   │       ├── Viewer.tsx
│   │       ├── MediaPool.tsx
│   │       ├── Inspector.tsx
│   │       ├── TimelinePanel.tsx
│   │       ├── AnalysisQueue.tsx
│   │       ├── BattleGallery.tsx
│   │       ├── UpdatePanel.tsx
│   │       ├── AiAnalysisPanel.tsx
│   │       ├── AdminPanel.tsx
│   │       ├── ClassDictionary.tsx
│   │       ├── NetworkPanel.tsx
│   │       ├── DebugPanel.tsx
│   │       ├── RulesPanel.tsx
│   │       └── Flight3D.tsx
│   ├── store/
│   │   ├── useRulesStore.ts
│   │   └── useReconStore.ts
│   ├── lib/reconRaycast.ts
│   └── types/muravei.ts
│
├── dist/                          # npm run build
├── assets/models/                 # yolo26n.pt, yolo26n-ft.pt, best.pt
├── runs/detect/train/weights/     # зеркало весов / YOLOE
├── archive/                       # медиа оператора
│   ├── crops/
│   ├── recordings/
│   ├── recon/
│   └── .trash/
├── cache/                         # train_run, backup_finetune_ds, …
├── logs/
├── reports/
├── scripts/
│   └── build_portable.ps1
├── portable/                      # stage + ZIP (артефакт сборки)
├── .cursor/rules/                 # agent rules (python env)
└── .backup/                       # LEGACY — не источник истины
```

## Что игнорировать при ориентировании

- `openreel-reference/` — справочный NLE-код, не runtime PRO.
- `portable/MuraveiVision_PRO_Portable/` — слепок сборки, править исходники в корне.
- `.backup/` — старые CONTEXT/ARCHITECTURE с устаревшими путями.
