# Network Setup — MuraveiVision PRO

> **Настройка сети: hub+client, JWT, WebSocket, firewall.**

## Обзор сети

MuraveiVision PRO поддерживает три режима сетевого взаимодействия:
- **Standalone** — одиночная машина
- **Hub** — центральный сервер
- **Client** — подключённый узел

## Топология сети

```
Hub+Client Topology:
                    ┌─────────────┐
                    │   HUB       │
                    │  Server     │
                    │ :8000 :8765 │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────┴─────┐ ┌───┴────┐ ┌────┴──────┐
        │ CLIENT 1  │ │CLIENT 2│ │CLIENT N  │
        │ :8000     │ │ :8000  │ │ :8000    │
        └───────────┘ └────────┘ └──────────┘

Ports:
• 8000 — HTTP API
• 8765 — WebSocket
• 443 — TLS (optional)
```

## Конфигурация Hub

```yaml
# config/custom.yaml — Hub
network:
  mode: "hub"
  host: "0.0.0.0"
  port: 8000
  ws_port: 8765

  # JWT
  jwt_secret: "your-hub-secret"
  jwt_algorithm: "HS256"

  # Clients
  allowed_clients:
    - "192.168.1.10"
    - "192.168.1.11"
    - "192.168.1.12"

  # Sync
  sync_interval_seconds: 30
  max_clients: 10
```

## Конфигурация Client

```yaml
# config/custom.yaml — Client
network:
  mode: "client"
  host: "0.0.0.0"
  port: 8000

  # Hub connection
  hub_url: "http://192.168.1.100:8000"
  hub_ws_url: "ws://192.168.1.100:8765"

  # Authentication
  client_id: "client_01"
  client_secret: "your-client-secret"

  # Sync
  sync_interval_seconds: 30
```

## WebSocket Channels

### N1-N6 Channels

| Channel | Name | Direction | Описание |
|---------|------|-----------|----------|
| **N1** | status | Bi-directional | Статус узлов |
| **N2** | detections | Client → Hub | Результаты обнаружения |
| **N3** | segments | Client → Hub | Данные сегментации |
| **N4** | chat | Bi-directional | Сообщения чата |
| **N5** | files | Bi-directional | Передача файлов |
| **N6** | location | Bi-directional | Геолокация |

### WebSocket configuration

```yaml
network:
  ws_port: 8765
  ws_channels:
    n1:
      name: "status"
      max_message_size: "1 KB"
      heartbeat_seconds: 30
    n2:
      name: "detections"
      max_message_size: "1 MB"
      batch_size: 10
    n3:
      name: "segments"
      max_message_size: "5 MB"
    n4:
      name: "chat"
      max_message_size: "10 KB"
      max_messages_per_sec: 5
    n5:
      name: "files"
      max_message_size: "100 MB"
      max_concurrent: 3
    n6:
      name: "location"
      max_message_size: "1 KB"
      interval_seconds: 10
```

## JWT Authentication

### Генерация secret

```bash
# Hub secret
muravei_env\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"

# Client secret (для каждого клиента)
muravei_env\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

### JWT Configuration

```yaml
security:
  jwt_secret: "hub-secret-here"
  jwt_algorithm: "HS256"
  jwt_expire_minutes: 1440
  jwt_refresh_enabled: true
  jwt_refresh_expire_hours: 336  # 14 days
```

### Token flow

```
Authentication Flow:
┌────────┐         ┌────────┐         ┌────────┐
│ Client │         │  Hub   │         │Client 2│
└───┬────┘         └───┬────┘         └───┬────┘
    │                  │                   │
    │  1. Login        │                   │
    │  ─────────────→  │                   │
    │                  │                   │
    │  2. Token        │                   │
    │  ←────────────── │                   │
    │                  │                   │
    │  3. Forward      │                   │
    │  ─────────────→  │                   │
    │                  │                   │
    │                  │  4. Relay         │
    │                  │  ─────────────→   │
    │                  │                   │
    │                  │  5. Response      │
    │                  │  ←──────────────  │
    │                  │                   │
    │  6. Response     │                   │
    │  ←────────────── │                   │
```

## Порты и Firewall

### Таблица портов

| Порт | Протокол | Направление | Назначение |
|------|----------|-------------|------------|
| **8000** | HTTP | In/Out | API |
| **8765** | WebSocket | In/Out | WS channels |
| **443** | HTTPS | In | TLS (optional) |
| **22** | SSH | In | Remote access |

### Firewall rules (Windows)

```batch
# Allow HTTP API
netsh advfirewall firewall add rule name="MuraveiVision API" ^
  dir=in action=allow protocol=TCP localport=8000

# Allow WebSocket
netsh advfirewall firewall add rule name="MuraveiVision WS" ^
  dir=in action=allow protocol=TCP localport=8765

# Allow HTTPS (optional)
netsh advfirewall firewall add rule name="MuraveiVision HTTPS" ^
  dir=in action=allow protocol=TCP localport=443
```

### Firewall rules (Linux)

```bash
# Allow HTTP API
sudo ufw allow 8000/tcp

# Allow WebSocket
sudo ufw allow 8765/tcp

# Allow HTTPS (optional)
sudo ufw allow 443/tcp
```

## TLS/SSL Setup

### Self-signed certificate

```bash
# Generate self-signed cert
muravei_env\Scripts\python.exe -c "
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import datetime

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
cert = x509.CertificateBuilder().subject_name(
    x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
).issuer_name(
    x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
).public_key(key.public_key()).serial_number(
    x509.random_serial_number()
).not_valid_before(datetime.datetime.utcnow()).not_valid_after(
    datetime.datetime.utcnow() + datetime.timedelta(days=365)
).sign(key, hashes.SHA256())

with open('cert.pem', 'wb') as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))
with open('key.pem', 'wb') as f:
    f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
"
```

### TLS Configuration

```yaml
network:
  tls:
    enabled: true
    cert_file: "cert.pem"
    key_file: "key.pem"
    verify_clients: false  # true for production
```

## IP Filtering

### Whitelist

```yaml
network:
  ip_filtering:
    enabled: true
    mode: "whitelist"  # whitelist | blacklist
    allowed_ips:
      - "192.168.1.0/24"
      - "10.0.0.0/8"
    blocked_ips: []
```

## Bandwidth Optimization

### Techniques

| Technique | Описание | Эффект |
|-----------|----------|--------|
| **Batching** | Группировка сообщений | -40% traffic |
| **Compression** | gzip сжатие | -60% traffic |
| **Delta updates** | Только изменения | -80% traffic |
| **Throttling** | Ограничение скорости | Контроль bandwidth |

### Bandwidth settings

```yaml
network:
  bandwidth:
    max_upload_mbps: 10
    max_download_mbps: 50
    compression: "gzip"
    batch_size: 10
    delta_updates: true
```

## Network Monitoring

### Проверка подключения

```bash
# Hub health
curl http://localhost:8000/health

# WebSocket test
muravei_env\Scripts\python.exe backend/scripts/ws_test.py \
  --url ws://localhost:8765

# Client connection
curl http://localhost:8000/api/network/status
```

### Мониторинг

```bash
# Network stats
muravei_env\Scripts\python.exe backend/scripts/network_monitor.py

# Connected clients
curl http://localhost:8000/api/network/clients

# Active channels
curl http://localhost:8000/api/network/channels
```

## Troubleshooting

### Проблема: Client не подключается

```
Client connection failed
Solution:
1. Проверьте hub_url в config
2. Проверьте firewall (port 8000, 8765)
3. Проверьте JWT secret (должен совпадать)
4. Проверьте logs на hub и client
```

### Проблема: WebSocket disconnects

```
WebSocket disconnections
Solution:
1. Увеличьте heartbeat (30s → 60s)
2. Проверьте NAT/路由器 timeout
3. Проверьте bandwidth
4. Проверьте max_clients limit
```

## Дальнейшие шаги

1. **[Maintenance](./MAINTENANCE.md)** — обслуживание
2. **[Diagnostics](./DIAGNOSTICS.md)** — диагностика
3. **[Updating](./UPDATING.md)** — обновление

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
