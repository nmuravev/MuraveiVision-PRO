# Portable Version — MuraveiVision PRO

> **Портативная версия: standalone distribution, air-gap deployment.**

## Overview

Portable version enables deployment without installation in air-gap environments.

## Package Contents

| Component | Size |
|-----------|------|
| Application | 500 MB |
| Python runtime | 300 MB |
| YOLO models | 6 MB |
| SAM3 | 1.5 GB |
| DA3-S | 2.1 GB |
| **Total** | **~4.4 GB** |

## Deployment Steps

```bash
# 1. Extract archive
tar -xzf MuraveiVision-PRO-portable.tar.gz
cd MuraveiVision-PRO-portable

# 2. Run launcher
start.bat

# 3. Open browser
# http://localhost:8000
```

## Air-Gap Preparation

```bash
# On internet-connected machine:
pip download -r requirements.txt -d ./packages
python backend/scripts/download_models.py --all

# Create archive
tar -a -c -f offline-package.tar.gz \
    MuraveiVision-PRO/ packages/

# Transfer via USB to air-gap machine
```

## Версия

- **Приложение:** v3.2.0
