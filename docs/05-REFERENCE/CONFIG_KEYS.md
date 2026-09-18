# Config Keys — MuraveiVision PRO

> **Все ключи конфигурации с описанием.**

## Main Configuration

```yaml
# config/custom.yaml

app:
  name: "MuraveiVision PRO"
  version: "3.2.0"
  debug: false

database:
  url: "sqlite:///data/muravei.db"
  wal_mode: true
  timeout: 30
  busy_timeout: 5000

gpu:
  device: "cuda"
  device_id: 0
  batch_size: 4
  fp16: true

sahi:
  enabled: true
  slice_height: 512
  slice_width: 512
  overlap_percentage: 20

security:
  jwt_secret: "generate-with-secrets-token-hex-32"
  jwt_algorithm: "HS256"
  jwt_expire_minutes: 1440

network:
  mode: "standalone"
  host: "0.0.0.0"
  port: 8000
```

## Key Descriptions

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `app.debug` | bool | false | Debug mode |
| `database.wal_mode` | bool | true | WAL mode |
| `gpu.device` | string | cuda | cuda/directml/cpu |
| `gpu.batch_size` | int | 4 | Inference batch |
| `sahi.slice_height` | int | 512 | SAHI tile height |
| `security.jwt_secret` | string | - | JWT secret (change!) |

## Версия

- **Приложение:** v3.2.0
