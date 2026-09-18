# Быстрый старт — Инженер

> **Цель:** Развернуть MuraveiVision PRO на рабочей машине за 15 минут.

## Предварительные требования

- Windows 10/11 с административными правами
- Доступ к GPU (NVIDIA CUDA или AMD DirectML)
- Сеть для первоначальной установки (офлайн-пакеты)
- 50 GB свободного места на SSD

## Шаг 1: Подготовка окружения

### 1.1 Установка Python

```bash
# Проверка наличия Python
python --version
# Должно быть: Python 3.10 — 3.12

# Если нет — установка из офлайн-установщика
# 1. На машине с интернетом:
#    https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
# 2. Скопируйте установщик на целевую машину
# 3. Запустите: python-3.11.9-amd64.exe /quiet InstallAllUsers=1
```

### 1.2 Создание виртуального окружения

```bash
# Создание окружения
python -m venv muravei_env

# Активация
muravei_env\Scripts\activate

# Проверка
python --version
# Python 3.11.9

where python
# D:\LLM\MuraveiVision-PRO\muravei_env\Scripts\python.exe
```

### 1.3 Установка CUDA (NVIDIA)

```bash
# Проверка наличия CUDA
nvidia-smi
# Должно показать CUDA version: 12.x

# Если CUDA не установлена:
# 1. Скачайте CUDA 12.4 Toolkit на машине с интернетом
# 2. Скопируйте на целевую машину
# 3. Запустите: cuda_12.4.0_windows.exe /quiet
# 4. Перезагрузите машину
```

### 1.4 Проверка GPU

```bash
# NVIDIA GPU
nvidia-smi
# Output:
# +-----------------------------------------------------------------------------+
# | NVIDIA-SMI 551.86       Driver Version: 551.86       CUDA Version: 12.4   |
# |-------------------------------+----------------------+----------------------+
# | GPU  Name        TCC/WDDM  | Bus-Id        Disp.A | Volatile Uncorr. ECC |
# | Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
# |   0  NVIDIA RTX 4070  WDDM  |   00000000:01:00.0  On |                  N/A |
# |  45%   52C    P8    12W / 200W |   2048MiB /  8192MiB |     5%      Default |
# +-----------------------------------------------------------------------------+

# AMD GPU
dxdiag /savefile dxdiag_report
# Проверьте вкладку "Display" — должно быть DirectML 1.11+
```

## Шаг 2: Установка приложения

### 2.1 Клонирование репозитория

```bash
# С сетью
git clone https://github.com/nmuravev/MuraveiVision-PRO.git
cd MuraveiVision-PRO

# Без сети (из офлайн-репозитория)
tar -xf MuraveiVision-PRO.tar.gz
cd MuraveiVision-PRO
```

### 2.2 Установка Python зависимостей

```bash
# Активация окружения
muravei_env\Scripts\activate

# С сетью
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Без сети (офлайн-пакеты)
pip install --no-index --find-links=./offline-packages -r requirements.txt
pip install --no-index --find-links=./offline-packages -r requirements-dev.txt

# Проверка
pip check
# Должно быть: No broken requirements found
```

### 2.3 Установка Node.js и frontend

```bash
# Проверка Node.js
node --version
# v18.19.0

npm --version
# 10.2.4

# Установка frontend зависимостей
cd MurVis
npm install

# Сборка
npm run build
# Output: built in 10.54s
```

### 2.4 Инициализация базы данных

```bash
# Создание БД и миграций
muravei_env\Scripts\python.exe backend/scripts/init_db.py

# Output:
# [OK] Database initialized: data/muravei.db
# [OK] Tables created: sessions, detections, segments, models, users
# [OK] Default user created: admin / admin (CHANGE THIS!)
# [OK] WAL mode enabled
```

## Шаг 3: Загрузка моделей

### 3.1 Загрузка YOLO моделей

```bash
# С сетью
muravei_env\Scripts\python.exe backend/scripts/download_models.py yolo

# Без сети
# 1. Скачайте модели на машине с интернетом:
#    https://github.com/nmuravev/MuraveiVision-PRO/releases/download/models/
#    - yolov8n.pt
#    - yolov8s.pt
#    - yolov11n.pt
# 2. Скопируйте в: backend/models/

# Проверка
dir backend\models\*.pt
# yolov8n.pt    6.1 MB
# yolov8s.pt   22.2 MB
# yolov11n.pt   6.3 MB
```

### 3.2 Загрузка SAM3 модели

```bash
# SAM3 требует ~1.5 GB
# С сетью
muravei_env\Scripts\python.exe backend/scripts/download_models.py sam3

# Без сети
# Скопируйте sam3_weights.bin в: backend/models/sam3/
```

### 3.3 Загрузка DA3 модели (опционально)

```bash
# DA3-S требует ~2.1 GB
# С сетью
muravei_env\Scripts\python.exe backend/scripts/download_models.py da3

# Без сети
# Скопируйте da3_s_weights.bin в: backend/models/da3/
```

### 3.4 Установка Ollama (AI-анализ)

```bash
# Установка Ollama
# 1. Скачайте с https://ollama.com
# 2. Запустите установщик
# 3. Загрузите модель:
ollama pull llama3.2
# Pulling complete
# Standalone server available at http://localhost:11434

# Проверка
ollama list
# NAME            ID           SIZE    MODIFIED
# llama3.2:latest 7a14b7017b7e 2.2 GB  2 days ago
```

## Шаг 4: Конфигурация

### 4.1 Файл конфигурации

```bash
# Создание файла конфигурации
copy config\example.yaml config\custom.yaml

# Редактирование config\custom.yaml
notepad config\custom.yaml
```

**Ключевые параметры:**

```yaml
# config/custom.yaml

# Database
database:
  url: sqlite:///data/muravei.db
  wal_mode: true
  backup_interval_hours: 24

# GPU
gpu:
  device: cuda          # cuda | directml | cpu
  device_id: 0
  batch_size: 4
  fp16: true

# SAHI
sahi:
  slice_height: 512
  slice_width: 512
  overlap_percentage: 20

# Security
security:
  jwt_secret: "CHANGE-ME-GENERATE-NEW-SECRET"
  jwt_algorithm: HS256
  rate_limit: 100/min

# Air-gap
airgap:
  enabled: true
  allow_updates: false
```

### 4.2 Генерация JWT secret

```bash
# Генерация случайного secret
muravei_env\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
# 'a1b2c3d4e5f6...'

# Вставьте в config/custom.yaml
```

## Шаг 5: Запуск приложения

### 5.1 Backend

```bash
# Активация окружения
muravei_env\Scripts\activate

# Запуск Uvicorn
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Output:
# INFO:     Uvicorn running on http://0.0.0.0:8000
# INFO:     Application startup complete.
# INFO:     Started process 12345
```

### 5.2 Frontend (отдельный терминал)

```bash
cd MurVis
npm run dev

# Output:
#   VITE v5.0.12  ready in 450 ms
#   ➜  Local:   http://localhost:5173/
#   ➜  Network: http://192.168.1.100:5173/
```

### 5.3 Проверка

```bash
# Backend health check
curl http://localhost:8000/health
# {"status": "ok", "version": "3.2.0", "gpu": "cuda"}

# Frontend
# Откройте http://localhost:5173
```

## Шаг 6: Первая аутентификация

### 6.1 Вход по умолчанию

```
Username: admin
Password: admin

⚠️  СРОЧНО СМЕНИТЕ ПАРОЛЬ ПО УМОЛЧАНИЮ!
```

### 6.2 Смена пароля

```
1. Меню → Settings → Users
2. Найти пользователя "admin"
3. Нажать "Change Password"
4. Ввести новый пароль (мин. 12 символов)
5. Подтвердить
```

## Шаг 7: Диагностика

### 7.1 Запуск полной диагностики

```bash
muravei_env\Scripts\python.exe backend/scripts/diagnose.py

# Output:
# ========================================
# MuraveiVision PRO — System Diagnostics
# ========================================
# [OK] Python 3.11.9
# [OK] CUDA 12.4, driver 551.86
# [OK] GPU: NVIDIA GeForce RTX 4070 (8 GB VRAM)
# [OK] AVX2: supported
# [OK] RAM: 16 GB (12 GB free)
# [OK] Disk: NVMe SSD (450 GB free)
# [OK] Database: initialized (WAL mode)
# [OK] Models: yolo, sam3, da3
# [WARN] Ollama: not installed
# [OK] Network: configured (hub mode)
# [OK] Security: JWT enabled
# [OK] Air-gap: enabled
# ========================================
# Status: READY
# ========================================
```

### 7.2 Smoke тесты

```bash
# Backend smoke tests
muravei_env\Scripts\python.exe -m pytest backend/tests/smoke/ -q
# 12 passed in 3.45s

# Frontend build check
cd MurVis && npm run build && cd ..
# built in 10.54s — 0 errors
```

## Шаг 8: Настройка резервного копирования

### 8.1 Автоматическое резервное копирование

```yaml
# config/custom.yaml
backup:
  enabled: true
  interval_hours: 24
  retention_days: 30
  destination: D:\backups\muravei\
  include_database: true
  include_models: false    # models are large, backup separately
  compress: true
```

### 8.2 Ручное резервное копирование

```bash
# Резервное копирование БД
muravei_env\Scripts\python.exe backend/scripts/backup.py --full

# Output:
# [OK] Backup created: data/backups/muravei_20260919_120000.db.gz
# [OK] Size: 1.2 MB (compressed)
# [OK] Checksum: sha256:a1b2c3d4...
```

## Troubleshooting

### Проблема: Backend не запускается

```
Error: ModuleNotFoundError: No module named 'fastapi'
Solution:
1. Убедитесь, что окружение активно: muravei_env\Scripts\activate
2. Проверьте pip: pip list | findstr fastapi
3. переустановите: pip install -r requirements.txt
```

### Проблема: Frontend не подключается к backend

```
Error: ERR_CONNECTION_REFUSED
Solution:
1. Проверьте, запущен ли backend: http://localhost:8000/health
2. Проверьте CORS в config/custom.yaml
3. Проверьте порт в MurVis/.env
```

### Проблема: GPU не используется

```
Error: CUDA out of memory
Solution:
1. Проверьте nvidia-smi
2. Уменьшите batch_size в config/custom.yaml
3. Закройте другие GPU-приложения
4. Перезапустите backend
```

## Дальнейшие шаги

1. **[Конфигурация](../02-ENGINEER/CONFIGURATION.md)** — детально про настройки
2. **[Аппаратное обеспечение](../02-ENGINEER/HARDWARE.md)** — GPU, CPU, RAM
3. **[Настройка сети](../02-ENGINEER/NETWORK_SETUP.md)** — hub+client режим
4. **[Обслуживание](../02-ENGINEER/MAINTENANCE.md)** — бэкапы, логи, обновление
5. **[Диагностика](../02-ENGINEER/DIAGNOSTICS.md)** — troubleshooting guide

## Поддержка

- **Документация:** [GLOSSARY.md](../GLOSSARY.md)
- **Диагностика:** [Diagnostics](../02-ENGINEER/DIAGNOSTICS.md)
- **GitHub:** [Issues](https://github.com/nmuravev/MuraveiVision-PRO/issues)
