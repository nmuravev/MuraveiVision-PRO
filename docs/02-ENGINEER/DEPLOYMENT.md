# Deployment — MuraveiVision PRO

> **Полное руководство по развёртыванию: dev, portable, field.**

## Обзор

MuraveiVision PRO поддерживает три режима развёртывания:
- **Dev setup** — локальная разработка
- **Portable build** — автономная дистрибуция
- **Field deployment** — полевая работа в air-gap

## Dev Setup

### Локальная разработка

```bash
# 1. Клонирование
git clone https://github.com/nmuravev/MuraveiVision-PRO.git
cd MuraveiVision-PRO

# 2. Python окружение
python -m venv muravei_env
muravei_env\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. Frontend
cd MurVis
npm install
npm run build
cd ..

# 4. База данных
muravei_env\Scripts\python.exe backend/scripts/init_db.py

# 5. Backend
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 6. Frontend (отдельный терминал)
cd MurVis
npm run dev
```

**Порты:**
| Сервис | Порт | Протокол |
|--------|------|----------|
| Backend API | 8000 | HTTP |
| Frontend | 5173 | HTTP |
| Ollama | 11434 | HTTP |

## Portable Build

### Создание дистрибутива

```
Portable package structure:
MuraveiVision-PRO-portable/
├── muravei_env/           # Python runtime
├── backend/               # Backend code
├── MurVis/                # Frontend (built)
├── models/                # Model weights
│   ├── yolo8n.pt          # 6 MB
│   ├── sam3_weights.bin   # 1.5 GB
│   └── da3_s_weights.bin  # 2.1 GB
├── config/
│   └── custom.yaml        # Configuration
├── data/                  # Runtime data
│   ├── muravei.db
│   └── logs/
├── start.bat              # Launcher
└── README.txt
```

### Создание пакета

```bash
# 1. Сборка frontend
cd MurVis
npm run build

# 2. Копирование моделей
mkdir models
copy backend\models\yolo8n.pt models\
copy backend\models\sam3\sam3_weights.bin models\
copy backend\models\da3\da3_s_weights.bin models\

# 3. Создание launch script
echo @echo off > start.bat
echo cd /d %%~dp0 >> start.bat
echo muravei_env\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 >> start.bat
echo start http://localhost:8000 >> start.bat

# 4. Архивирование
tar -a -c -f MuraveiVision-PRO-portable.zip MuraveiVision-PRO-portable/
```

### Размер пакета

| Компонент | Размер |
|-----------|--------|
| Приложение | 500 MB |
| Python runtime | 300 MB |
| YOLOv8n | 6 MB |
| SAM3 | 1.5 GB |
| DA3-S | 2.1 GB |
| **Итого** | **~4.4 GB** |

## Field Deployment

### Air-gap развёртывание

```
Air-gap deployment workflow:
┌──────────────────┐         ┌──────────────────┐
│  Internet machine │  ──→   │  Air-gap machine  │
│                  │  USB    │                  │
│  1. Download     │         │  1. Copy files   │
│     packages     │         │     from USB     │
│  2. Create pack  │         │  2. Install      │
│     age          │         │     offline      │
│  3. Copy to USB  │         │  3. Configure    │
└──────────────────┘         └──────────────────┘
```

### Offline packages

```bash
# На машине с интернетом
pip download -r requirements.txt -d ./offline-py-packages
pip download -r requirements-dev.txt -d ./offline-py-packages-dev

# npm packages (если нужно)
cd MurVis
npm pack
cd ..

# Создание архива
tar -a -c -f MuraveiVision-PRO-offline.tar.gz \
    MuraveiVision-PRO/ \
    offline-py-packages/ \
    MurVis/*.tgz
```

### Установка на air-gap машине

```bash
# 1. Распаковка
tar -xzf MuraveiVision-PRO-offline.tar.gz
cd MuraveiVision-PRO

# 2. Python установка
python -m venv muravei_env
muravei_env\Scripts\activate
pip install --no-index --find-links=../offline-py-packages -r requirements.txt
pip install --no-index --find-links=../offline-py-packages-dev -r requirements-dev.txt

# 3. Frontend
cd MurVis
npm install --offline
npm run build
cd ..

# 4. БД
muravei_env\Scripts\python.exe backend/scripts/init_db.py

# 5. Запуск
muravei_env\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

## Windows Service

### Установка как служба

```batch
@echo off
REM Install as Windows Service
cd /d D:\LLM\MuraveiVision-PRO

muravei_env\Scripts\python.exe -m pip install pywin32 services

REM Создать service.py
echo import win32serviceutil >> service.py
echo import win32service >> service.py
echo import win32event >> service.py
echo import uvicorn >> service.py
echo. >> service.py
echo class MuraveiVisionSvc(win32serviceutil.ServiceFramework): >> service.py
echo     _svc_name_ = 'MuraveiVision' >> service.py
echo     _svc_display_name_ = 'MuraveiVision PRO' >> service.py
echo. >> service.py
echo     def SvcRun(self): >> service.py
echo         uvicorn.run('main:app', host='0.0.0.0', port=8000) >> service.py
echo. >> service.py
echo if __name__ == '__main__': >> service.py
echo     win32serviceutil.HandleCommandLine(MuraveiVisionSvc) >> service.py

REM Install
muravei_env\Scripts\python.exe service.py --install
net start MuraveiVision
```

### Управление службой

```batch
# Start
net start MuraveiVision

# Stop
net stop MuraveiVision

# Uninstall
muravei_env\Scripts\python.exe service.py --remove

# View logs
type data\logs\service.log
```

## Docker Deployment (Optional)

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY backend/ backend/
COPY MurVis/dist/ frontend/

# Copy models
COPY models/ models/

# Expose ports
EXPOSE 8000

# Run
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Build and run

```bash
# Build
docker build -t muraveivision/pro:3.2.0 .

# Run
docker run -d \
  --name muravei-vision \
  --gpus all \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/models:/app/models \
  muraveivision/pro:3.2.0
```

## Post-deployment Verification

### Check list

```
Post-deployment checklist:
┌─────────────────────────────────────────┐
│  ☐ Python version: 3.10-3.12           │
│  ☐ Dependencies installed: pip check   │
│  ☐ Frontend built: npm run build       │
│  ☐ Database initialized: init_db.py    │
│  ☐ Models downloaded: models/          │
│  ☐ Config created: custom.yaml         │
│  ☐ Backend running: curl /health       │
│  ☐ Frontend accessible: :5173          │
│  ☐ GPU detected: nvidia-smi            │
│  ☐ Ollama running: ollama list         │
│  ☐ Backup configured: backup.yaml      │
│  ☐ Admin password changed              │
│  ☐ Logs writable: data/logs/           │
│  ☐ Disk space: >20 GB free             │
└─────────────────────────────────────────┘
```

### Automated verification

```bash
# Run all smoke tests
muravei_env\Scripts\python.exe -m pytest backend/tests/smoke/ -q

# Health check
curl http://localhost:8000/health
# {"status": "ok", "version": "3.2.0", "gpu": "cuda"}

# Frontend check
curl http://localhost:5173
# HTTP 200
```

## Rollback Procedures

### Rollback backend

```bash
# 1. Остановить backend
# (Ctrl+C или net stop MuraveiVision)

# 2. Восстановить предыдущую версию
git checkout v3.1.0

# 3. Переустановить зависимости
pip install -r requirements.txt

# 4. Запустить
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Rollback frontend

```bash
cd MurVis

# 1. Предыдущая версия
git checkout v3.1.0
npm install
npm run build

# 2. Перезапустить dev server или обновить dist/
```

### Rollback database

```bash
# 1. Восстановить БД из backup
copy data\backups\muravei_20260918.db data\muravei.db

# 2. Проверить целостность
muravei_env\Scripts\python.exe backend/scripts/db_check.py
```

## Дальнейшие шаги

1. **[Configuration](./CONFIGURATION.md)** — настройка параметров
2. **[Models](./MODELS.md)** — управление моделями
3. **[Hardware](./HARDWARE.md)** — оборудование
4. **[Maintenance](./MAINTENANCE.md)** — обслуживание

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
