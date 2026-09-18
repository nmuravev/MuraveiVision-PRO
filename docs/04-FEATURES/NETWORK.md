# Network v3.3 — MuraveiVision PRO

> **Сетевое взаимодействие: hub+client, JWT, WebSocket N1-N6.**

## Overview

Network v3.3 enables multi-machine target synchronization.

## Architecture

```
Hub+Client Topology:
        ┌──────────┐
        │   HUB    │
        │ :8000    │
        └────┬─────┘
             │
      ┌──────┼──────┐
      │      │      │
   Client  Client  Client
    1:8000  2:8000  3:8000
```

## WebSocket Channels

| Channel | Name | Direction | Description |
|---------|------|-----------|-------------|
| N1 | status | Bi-directional | Node status |
| N2 | detections | Client → Hub | Detection results |
| N3 | segments | Client → Hub | Segmentation data |
| N4 | chat | Bi-directional | Chat messages |
| N5 | files | Bi-directional | File transfer |
| N6 | location | Bi-directional | Location sharing |

## JWT Authentication

```yaml
security:
  jwt_secret: "generated-secret"
  jwt_algorithm: "HS256"
  jwt_expire_minutes: 1440
```

## Версия

- **Приложение:** v3.2.0
