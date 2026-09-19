# Models — MuraveiVision PRO

> **Управление моделями: веса, импорт из USB, class catalog.**

## Обзор

MuraveiVision PRO использует несколько моделей для различных задач: обнаружение (YOLO), сегментация (SAM3), глубина (DA3), AI-анализ (Ollama).

## Model Inventory

### Список моделей

| Модель | Назначение | Размер | Путь |
|--------|------------|--------|------|
| **YOLO26n** | Detection (fast) | 6 MB | `models/yolo26n.pt` |
| **YOLO26s** | Detection (balanced) | 22 MB | `models/yolo26s.pt` |
| **YOLO26m** | Detection (accurate) | 51 MB | `models/yolo26m.pt` |
| **SAM3** | Segmentation | 1.5 GB | `models/sam3/sam3_weights.bin` |
| **DA3-S** | Depth estimation | 2.1 GB | `models/da3/da3_s_weights.bin` |
| **DA3-B** | Depth estimation (large) | 4.3 GB | `models/da3/da3_b_weights.bin` |
| **llama3.2** | AI analysis | 2.2 GB | `ollama:llama3.2` |

### Total storage

```
Model storage requirements:
┌─────────────────────────────────────────┐
│  Minimal (YOLO only):       6 MB        │
│  Standard (+ SAM3):       1.5 GB       │
│  Full (+ DA3-S):          3.6 GB       │
│  Complete (+ DA3-B):      5.8 GB       │
│  Complete (+ Ollama):     8.0 GB       │
└─────────────────────────────────────────┘
```

## Model Weights Management

### Download models

```bash
# Download all models
muravei_env\Scripts\python.exe backend/scripts/download_models.py --all

# Download specific model
muravei_env\Scripts\python.exe backend/scripts/download_models.py \
  --model yolo26s

# Download DA3 (new in v3.2.0)
muravei_env\Scripts\python.exe backend/scripts/download_models.py \
  --model da3 --variant s
```

### Offline download

```bash
# On internet-connected machine
pip download -r requirements.txt -d ./packages

# Download models
python backend/scripts/download_models.py --all --output ./models-package

# Create archive
tar -a -c -f MuraveiVision-models.tar.gz models-package/
```

### Verify models

```bash
# Verify all models
muravei_env\Scripts\python.exe backend/scripts/verify_models.py

# Output:
# ========================================
# Model Verification
# ========================================
# [OK] yolo26s.pt — size: 22 MB, checksum: valid
# [OK] sam3_weights.bin — size: 1.5 GB, checksum: valid
# [OK] da3_s_weights.bin — size: 2.1 GB, checksum: valid
# [OK] All models verified
# ========================================
```

## Import from USB

### Подготовка на машине с интернетом

```bash
# 1. Download models
python backend/scripts/download_models.py --all --output D:\USB\models\

# 2. Copy application to USB
xcopy MuraveiVision-PRO D:\USB\app\ /E /I

# 3. Create import script
echo @echo off > D:\USB\import_models.bat
echo cd /d %%~dp0 >> D:\USB\import_models.bat
echo python import_models.py models\ >> D:\USB\import_models.bat
```

### Импорт на air-gap машине

```bash
# Copy from USB
xcopy E:\models\ backend\models\ /E /I

# Verify
muravei_env\Scripts\python.exe backend/scripts/verify_models.py

# Or use import script
python backend/scripts/import_models.py E:\models\
```

### USB import script

```python
# backend/scripts/import_models.py
import shutil
import sys
from pathlib import Path

def import_models(source_dir):
    """Import models from USB source."""
    source = Path(source_dir)
    dest = Path("backend/models")
    dest.mkdir(parents=True, exist_ok=True)
    
    for model_file in source.glob("*.pt"):
        dest_file = dest / model_file.name
        shutil.copy2(model_file, dest_file)
        print(f"[OK] Imported: {model_file.name}")
    
    for model_file in source.glob("*.bin"):
        dest_file = dest / model_file.name
        shutil.copy2(model_file, dest_file)
        print(f"[OK] Imported: {model_file.name}")

if __name__ == "__main__":
    import_models(sys.argv[1])
```

## Class Catalog

### Определение классов

```yaml
# config/class_catalog.yaml
classes:
  - id: 0
    name: "ant_worker"
    display: "Ant Worker"
    color: "#FF0000"
    category: "ant"
    
  - id: 1
    name: "ant_queen"
    display: "Ant Queen"
    color: "#FF00FF"
    category: "ant"
    
  - id: 2
    name: "ant_soldier"
    display: "Ant Soldier"
    color: "#FF6600"
    category: "ant"
    
  - id: 3
    name: "cricket"
    display: "Cricket"
    color: "#0000FF"
    category: "insect"
    
  - id: 4
    name: "beetle"
    display: "Beetle"
    color: "#00FF00"
    category: "insect"
```

### Editing classes

```bash
# View current classes
muravei_env\Scripts\python.exe backend/scripts/class_catalog.py --view

# Add new class
muravei_env\Scripts\python.exe backend/scripts/class_catalog.py \
  --add --name "spider" --display "Spider" --color "#FFFF00"

# Remove class
muravei_env\Scripts\python.exe backend/scripts/class_catalog.py \
  --remove --name "obsolete_class"

# Export catalog
muravei_env\Scripts\python.exe backend/scripts/class_catalog.py \
  --export catalog.json
```

### Class colors

```yaml
# config/class_colors.yaml
colors:
  ant_worker: "#FF0000"    # Red
  ant_queen: "#FF00FF"     # Magenta
  ant_soldier: "#FF6600"   # Orange
  cricket: "#0000FF"       # Blue
  beetle: "#00FF00"        # Green
  spider: "#FFFF00"        # Yellow
  larva: "#800080"         # Purple
```

## Model Versioning

### Version management

```
Model versions:
┌─────────────────────────────────────────┐
│  yolo26s-ft:                             │
│  Current: v3.0 (2026-09-19)            │
│  Previous: v2.0 (2026-08-01)           │
│  Available: v1.0, v2.0, v3.0           │
│                                         │
│  sam3:                                  │
│  Current: v1.1 (2026-09-19)            │
│  Available: v1.0, v1.1                 │
│                                         │
│  da3:                                   │
│  Current: v1.0 (2026-09-19)            │
│  Available: v1.0                       │
└─────────────────────────────────────────┘
```

### Switching models

```bash
# List available models
muravei_env\Scripts\python.exe backend/scripts/model_manager.py --list

# Switch detection model
muravei_env\Scripts\python.exe backend/scripts/model_manager.py \
  --set-detection yolo26n

# Switch segmentation model
muravei_env\Scripts\python.exe backend/scripts/model_manager.py \
  --set-segmentation sam3-v1.1

# Verify active models
muravei_env\Scripts\python.exe backend/scripts/model_manager.py --status
```

## Model Optimization

### Quantization

```bash
# Quantize YOLO model (INT8)
muravei_env\Scripts\python.exe backend/scripts/quantize.py \
  --model models/yolo26s.pt \
  --output models/yolo26s-int8.pt \
  --format int8

# Size reduction: 22 MB → 6 MB (3x smaller)
# Speed increase: ~1.5x faster
# Accuracy loss: ~1-2% mAP
```

### Pruning

```bash
# Prune model (remove unnecessary weights)
muravei_env\Scripts\python.exe backend/scripts/prune.py \
  --model models/yolo26s.pt \
  --output models/yolo26s-pruned.pt \
  --sparsity 0.3

# Size reduction: 22 MB → 15 MB
# Speed increase: ~1.3x faster
# Accuracy loss: ~0.5% mAP
```

## Model Health Checks

### Automated checks

```bash
# Check model health
muravei_env\Scripts\python.exe backend/scripts/model_health.py

# Output:
# ========================================
# Model Health Check
# ========================================
# [OK] yolo26s — loaded, inference OK, mAP: 44.9
# [OK] sam3 — loaded, inference OK, FPS: 30
# [OK] da3_s — loaded, inference OK, FPS: 12
# [OK] All models healthy
# ========================================
```

### Manual inference test

```bash
# Test detection
muravei_env\Scripts\python.exe backend/scripts/test_inference.py \
  --type detection --image test_image.jpg

# Test segmentation
muravei_env\Scripts\python.exe backend/scripts/test_inference.py \
  --type segmentation --image test_image.jpg

# Test depth
muravei_env\Scripts\python.exe backend/scripts/test_inference.py \
  --type depth --image test_image.jpg
```

## Troubleshooting

### Проблема: Модель не загружается

```
Model failed to load
Solution:
1. Verify checksum: verify_models.py
2. Check file size (compare with expected)
3. Re-download model
4. Check GPU memory (VRAM)
```

### Проблема: Мало VRAM для модели

```
Out of VRAM
Solution:
1. Use smaller model (yolo26n instead of yolo26s)
2. Quantize model (INT8)
3. Close other GPU applications
4. Reduce batch_size in config
```

## Дальнейшие шаги

1. **[Hardware](./HARDWARE.md)** — оборудование
2. **[Configuration](./CONFIGURATION.md)** — настройка
3. **[Maintenance](./MAINTENANCE.md)** — обслуживание

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
