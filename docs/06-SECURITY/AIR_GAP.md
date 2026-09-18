# Air-Gap Mode — MuraveiVision PRO

> **Air-gap режим: enforcement, offline packages.**

## Policy

```yaml
airgap:
  enabled: true
  allow_updates: false
  allow_downloads: false
```

## Enforcement

- No PyPI imports at runtime
- No HuggingFace downloads
- No GitHub API calls
- No external API calls

## Preparation

```bash
# On internet machine:
pip download -r requirements.txt -d ./packages
python backend/scripts/download_models.py --all

# Transfer via USB to air-gap machine
```

## Версия

- **Приложение:** v3.2.0
