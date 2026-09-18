# Сетевая интеграция v3.3

## Обзор

Сетевая подсистема MuraveiVision PRO v3.3 обеспечивает многомашинную синхронизацию целей между узлами через архитектуру Hub+Client. Система поддерживает JWT-аутентификацию, WebSocket-каналы для различных типов данных, чат, обмен местоположением и синхронизацию файлов.

## Архитектура Hub+Client

### Диаграмма топологии

```
┌──────────────────────────────────────────────────────────────────────┐
│                        СЕТЕВАЯ ТОПОЛОГИЯ                              │
│                                                                      │
│                    ┌─────────────────────┐                           │
│                    │                     │                           │
│                    │     HUB SERVER      │                           │
│                    │   (Центральный узел) │                           │
│                    │                     │                           │
│                    │  ┌───────────────┐  │                           │
│                    │  │  JWT Auth     │  │                           │
│                    │  │  Session Mgmt │  │                           │
│                    │  └───────┬───────┘  │                           │
│                    │          │          │                           │
│                    │  ┌───────┴───────┐  │                           │
│                    │  │  Message      │  │                           │
│                    │  │  Broker       │  │                           │
│                    │  └───────┬───────┘  │                           │
│                    │          │          │                           │
│                    │  ┌───────┴───────┐  │                           │
│                    │  │  Target       │  │                           │
│                    │  │  Sync Engine  │  │                           │
│                    │  └───────┬───────┘  │                           │
│                    │          │          │                           │
│                    │  ┌───────┴───────┐  │                           │
│                    │  │  File         │  │                           │
│                    │  │  Sync Engine  │  │                           │
│                    │  └───────────────┘  │                           │
│                    └────────┬───────────┘                           │
│                             │ TCP/WS                                │
│              ┌──────────────┼──────────────┐                        │
│              │              │              │                         │
│     ┌────────┴──┐   ┌──────┴──────┐  ┌────┴────────┐               │
│     │           │   │             │  │             │               │
│     │ CLIENT 1  │   │ CLIENT 2   │  │ CLIENT N    │               │
│     │ (Нода 1)  │   │ (Нода 2)   │  │ (Нода N)    │               │
│     │           │   │             │  │             │               │
│     │ • Детекция│   │ • Детекция │  │ • Детекция  │               │
│     │ • Сегмент.│   │ • Сегмент. │  │ • Сегмент.  │               │
│     │ • Чат     │   │ • Чат      │  │ • Чат       │               │
│     │ • Локация │   │ • Локация  │  │ • Локация   │               │
│     │ • Файлы   │   │ • Файлы    │  │ • Файлы     │               │
│     └───────────┘   └────────────┘  └─────────────┘               │
│                                                                      │
│  Все клиенты подключены к Hub. Hub маршрутизирует данные между     │
│  клиентами и обеспечивает синхронизацию целей.                       │
└──────────────────────────────────────────────────────────────────────┘
```

### Топологии сети

| Топология | Описание | Преимущества | Недостатки |
|-----------|----------|-------------|------------|
| **Hub+Client** | Центральный сервер + клиенты | Простота, централизованное управление | Единая точка отказа |
| **Mesh** | Все узлы связаны | Отказоустойчивость | Сложность настройки |
| **Hybrid** | Несколько Hub + клиенты | Масштабируемость | Сложная архитектура |

## JWT-аутентификация

### Схема аутентификации

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│  Client  │     │  Auth Server │     │  Resource    │
│          │     │              │     │  Server      │
│          │     │              │     │              │
│ 1. Login │     │              │     │              │
│ ────────>│     │              │     │              │
│          │ 2. │              │     │              │
│          │────>│ Validate     │     │              │
│          │     │ Credentials  │     │              │
│          │     └──────┬───────┘     │              │
│          │            │             │              │
│          │            │ 3. Return   │              │
│          │            │ JWT Token   │              │
│ 4. JWT  │            │             │              │
│ ────────│─────────────────────────>│              │
│          │            │             │              │
│          │            │             │ 5. Validate  │
│          │            │             │ ────────────>│
│          │            │             │              │
│          │            │             │ 6. Return    │
│          │            │             │    Data      │
│          │<─────────────────────────│              │
```

### Настройка JWT

```yaml
# network_auth.yaml
jwt:
  # Секретный ключ (минимум 32 символа)
  secret: "${JWT_SECRET}"
  
  # Алгоритм подписи
  algorithm: "HS256"
  
  # Срок действия токена
  access_token_expire_minutes: 60
  refresh_token_expire_days: 7
  
  # Пользователи
  users:
    - username: "operator1"
      password_hash: "$2b$12$..."  # bcrypt хеш
      role: "operator"
      permissions:
        - "detect"
        - "segment"
        - "chat"
        - "location"
        - "file_sync"
        - "target_view"
        
    - username: "admin"
      password_hash: "$2b$12$..."
      role: "admin"
      permissions:
        - "*"  # все права

  # Роли
  roles:
    admin:
      - "*"
    operator:
      - "detect"
      - "segment"
      - "chat"
      - "location"
      - "file_sync"
      - "target_view"
    viewer:
      - "target_view"
      - "chat"
```

### Генерация токенов

```python
import jwt
import datetime
from functools import wraps

# Конфигурация
JWT_SECRET = "your-secure-secret-key-min-32-chars"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = datetime.timedelta(minutes=60)
REFRESH_TOKEN_EXPIRE = datetime.timedelta(days=7)

def create_access_token(username: str, role: str, permissions: list) -> str:
    """Создание JWT access токена."""
    now = datetime.datetime.utcnow()
    payload = {
        "sub": username,
        "role": role,
        "permissions": permissions,
        "iat": now,
        "exp": now + ACCESS_TOKEN_EXPIRE,
        "type": "access"
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def create_refresh_token(username: str) -> str:
    """Создание JWT refresh токена."""
    now = datetime.datetime.utcnow()
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + REFRESH_TOKEN_EXPIRE,
        "type": "refresh"
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token: str) -> dict:
    """Верификация JWT токена."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")

def require_permission(permission: str):
    """Декоратор для проверки разрешения."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Проверка токена из заголовка
            token = get_token_from_header()
            payload = verify_token(token)
            
            if permission not in payload.get("permissions", []):
                raise PermissionError(f"Required permission: {permission}")
            
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

### Заголовки авторизации

```bash
# Использование токена в запросах
curl -H "Authorization: Bearer <access_token>" \
     http://hub-server:8080/api/v1/targets

# Refresh токена
curl -X POST http://hub-server:8080/api/v1/auth/refresh \
     -H "Content-Type: application/json" \
     -d '{"refresh_token": "<refresh_token>"}'
```

## WebSocket-каналы (N1-N6)

### Обзор каналов

MuraveiVision PRO использует 6 WebSocket-каналов для различных типов данных:

```
┌────────────────────────────────────────────────────────────────┐
│                    WebSocket Каналы                             │
│                                                                │
│  N1 ───► Target Sync Channel                                  │
│         ┌────────────────���─────────────────────┐               │
│         │ • Обнаруженные цели                   │               │
│         │ • Координаты целей                   │               │
│         │ • Классы объектов                    │               │
│         │ • Уверенность                        │               │
│         │ • Timestamp                          │               │
│         └──────────────────────────────────────┘               │
│                                                                │
│  N2 ───► Segmentation Channel                                 │
│         ┌──────────────────────────────────────┐               │
│         │ • Маски сегментации                  │               │
│         │ • Пропущенные кадры                  │               │
│         │ • Polygon data                       │               │
│         └──────────────────────────────────────┘               │
│                                                                │
│  N3 ───► Chat Channel                                         │
│         ┌──────────────────────────────────────┐               │
│         │ • Сообщения                          │               │
│         │ • Эмодзи/реакции                     │               │
│         │ • Уведомления                        │               │
│         └──────────────────────────────────────┘               │
│                                                                │
│  N4 ───► Location Channel                                     │
│         ┌──────────────────────────────────────┐               │
│         │ • Позиция оператора                  │               │
│         │ • Направление камеры                 │               │
│         │ • GPS координаты                     │               │
│         │ • Состояние системы                  │               │
│         └──────────────────────────────────────┘               │
│                                                                │
│  N5 ───► File Sync Channel                                    │
│         ┌──────────────────────────────────────┐               │
│         │ • Файлы изображений                  │               │
│         │ • Модели ML                          │               │
│         │ • Конфигурации                       │               │
│         │ • Логи                               │               │
│         └──────────────────────────────────────┘               │
│                                                                │
│  N6 ───► Control Channel                                      │
│         ┌──────────────────────────────────────┐               │
│         │ • Команды управления                 │               │
│         │ • Состояние узлов                    │               │
│         │ • Heartbeat                          │               │
│         │ • Ошибки                             │               │
│         └──────────────────────────────────────┘               │
└────────────────────────────────────────────────────────────────┘
```

### Таблица каналов

| Канал | ID | Тип данных | Пропускная способность | Приоритет |
|-------|-----|-----------|----------------------|-----------|
| Target Sync | N1 | Цели детекции | ~100 msg/сек | Высокий |
| Segmentation | N2 | Маски | ~30 msg/сек | Высокий |
| Chat | N3 | Сообщения | ~10 msg/сек | Средний |
| Location | N4 | Локация | ~5 msg/сек | Средний |
| File Sync | N5 | Файлы | ~10 MB/сек | Низкий |
| Control | N6 | Управление | ~5 msg/сек | Критический |

### Пример WebSocket-соединения

```python
import asyncio
import websockets
import json
import time

class MuraveiVisionWebSocket:
    """Клиент WebSocket для MuraveiVision PRO."""
    
    def __init__(self, hub_url: str, token: str):
        self.hub_url = hub_url
        self.token = token
        self.channels = {}
        
    async def connect(self):
        """Подключение ко всем каналам."""
        url = f"{self.hub_url}?token={self.token}"
        
        # Подключение к каждому каналу
        for channel_id in ["N1", "N2", "N3", "N4", "N5", "N6"]:
            ws_url = f"{url}&channel={channel_id}"
            websocket = await websockets.connect(ws_url)
            self.channels[channel_id] = websocket
            
        print(f"Connected to all channels via {self.hub_url}")
        
    async def send_target(self, target_data: dict):
        """Отправка данных о цели через N1."""
        message = {
            "type": "target",
            "timestamp": time.time(),
            "node_id": "node_001",
            "targets": target_data
        }
        await self.channels["N1"].send(json.dumps(message))
        
    async def send_chat_message(self, text: str, recipient: str = None):
        """Отправка сообщения в чат через N3."""
        message = {
            "type": "chat_message",
            "timestamp": time.time(),
            "sender": "operator1",
            "text": text,
            "recipient": recipient
        }
        await self.channels["N3"].send(json.dumps(message))
        
    async def send_location(self, lat: float, lon: float, heading: float = None):
        """Отправка местоположения через N4."""
        message = {
            "type": "location",
            "timestamp": time.time(),
            "node_id": "node_001",
            "latitude": lat,
            "longitude": lon,
            "heading": heading
        }
        await self.channels["N4"].send(json.dumps(message))
        
    async def receive_targets(self):
        """Приём данных о целях."""
        async for message in self.channels["N1"]:
            data = json.loads(message)
            print(f"Received {len(data.get('targets', []))} targets")
            
    async def receive_chat(self):
        """Приём сообщений чата."""
        async for message in self.channels["N3"]:
            data = json.loads(message)
            print(f"[{data.get('sender')}] {data.get('text')}")
```

## Обмен целями между узлами

### Схема синхронизации

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  Node 1  │     │  HUB     │     │  Node 2  │
│          │     │          │     │          │
│ Detect   │     │          │     │          │
│ Targets  │────>│  Relay   │────>│ Detect   │
│          │     │  Targets │     │ Targets  │
│          │<────│          │<────│          │
│  View    │     │          │     │  View    │
│ Remote   │     │          │     │ Remote   │
│ Targets  │     │          │     │ Targets  │
└──────────┘     └──────────┘     └──────────┘
```

### Формат данных цели

```json
{
    "target_id": "tgt_20240115_001",
    "node_id": "node_001",
    "timestamp": 1705312800.0,
    "image_id": "img_001.jpg",
    "bounding_box": {
        "x": 120,
        "y": 80,
        "width": 60,
        "height": 90
    },
    "normalized_box": {
        "x": 0.2,
        "y": 0.16,
        "width": 0.1,
        "height": 0.15
    },
    "class_id": 0,
    "class_name": "beetle",
    "confidence": 0.95,
    "segmentation": null,
    "metadata": {
        "camera_id": "cam_001",
        "resolution": [1920, 1080]
    }
}
```

### Политика синхронизации

| Параметр | Значение | Описание |
|----------|----------|----------|
| `sync_interval_ms` | 500 | Интервал синхронизации |
| `max_targets_per_msg` | 50 | Макс. целей в сообщении |
| `ttl_seconds` | 300 | Время жизни цели |
| `dedup_window_ms` | 1000 | Окно дедупликации |
| `priority` | `high` | Приоритет канала |

## Чат-функциональность

### Формат сообщений

```json
{
    "message_id": "msg_20240115_001",
    "type": "text",
    "sender": {
        "node_id": "node_001",
        "username": "operator1",
        "display_name": "Оператор 1"
    },
    "text": "Обнаружена группа жуков в секторе B",
    "timestamp": 1705312800.0,
    "reactions": [],
    "reply_to": null,
    "mentions": ["operator2"]
}
```

### Типы сообщений

| Тип | Описание |
|-----|----------|
| `text` | Текстовое сообщение |
| `alert` | Системное уведомление |
| `target_share` | Поделиться целью |
| `location_share` | Поделиться локацией |
| `file_share` | Поделиться файлом |

## Обмен местоположением

### Формат данных локации

```json
{
    "location_id": "loc_20240115_001",
    "node_id": "node_001",
    "timestamp": 1705312800.0,
    "gps": {
        "latitude": 55.7558,
        "longitude": 37.6173,
        "altitude": 150.0,
        "accuracy": 5.0
    },
    "orientation": {
        "heading": 180.0,
        "pitch": -10.0,
        "roll": 0.0
    },
    "camera": {
        "id": "cam_001",
        "fov_horizontal": 60.0,
        "fov_vertical": 45.0
    }
}
```

## Синхронизация файлов

### Типы файлов

| Тип | Описание | Размер |
|-----|----------|--------|
| `image` | Изображения для обработки | 1-10 MB |
| `model` | ML модели | 10-200 MB |
| `config` | Конфигурации | 1-10 KB |
| `log` | Файлы логов | 1-50 MB |
| `reconstruction` | Результаты 3D реконструкции | 50-500 MB |

### Процесс синхронизации

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  Source  │     │  HUB     │     │  Target  │
│  Node    │     │          │     │  Node    │
│          │     │          │     │          │
│ 1. Upload│     │          │     │          │
│ ────────>│ 2.  │          │     │          │
│          │────>│  Verify  │     │          │
│          │     │ ────────>│     │          │
│          │     │          │     │ 3. Download│
│          │     │          │<────│          │
│          │     │          │     │          │
│ 4. Ack   │     │ 5. Ack   │     │          │
│ <───────│────>│ <─────── │     │          │
└──────────┘     └──────────┘     └──────────┘
```

## Настройка сети

### Пример конфигурации

```yaml
# network_config.yaml
network:
  # Hub сервер
  hub:
    host: "0.0.0.0"
    port: 8080
    ws_port: 8081
    max_clients: 50
    
  # Клиент
  client:
    hub_url: "ws://hub-server:8081"
    reconnect_interval: 5
    max_reconnect_attempts: 10
    
  # Каналы
  channels:
    N1:
      name: "target_sync"
      enabled: true
      max_messages_per_second: 100
      buffer_size: 1000
      
    N2:
      name: "segmentation"
      enabled: true
      max_messages_per_second: 30
      buffer_size: 500
      
    N3:
      name: "chat"
      enabled: true
      max_messages_per_second: 10
      buffer_size: 200
      
    N4:
      name: "location"
      enabled: true
      max_messages_per_second: 5
      buffer_size: 100
      
    N5:
      name: "file_sync"
      enabled: true
      max_bandwidth_mbps: 10
      max_file_size_mb: 500
      
    N6:
      name: "control"
      enabled: true
      max_messages_per_second: 5
      buffer_size: 50
      
  # Heartbeat
  heartbeat:
    interval_seconds: 10
    timeout_seconds: 30
    
  # Лимиты
  rate_limiting:
    enabled: true
    default_limit: 60
    window_seconds: 60
```

## API для сетевых операций

### POST /api/v1/network/auth/login

Вход в систему.

```json
// Request
{
    "username": "operator1",
    "password": "secure_password"
}

// Response
{
    "status": "success",
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_in": 3600,
    "user": {
        "username": "operator1",
        "role": "operator",
        "permissions": ["detect", "segment", "chat", "location", "file_sync", "target_view"]
    }
}
```

### POST /api/v1/network/auth/refresh

Обновление токена.

```json
// Request
{
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}

// Response
{
    "status": "success",
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_in": 3600
}
```

### GET /api/v1/network/nodes

Список подключённых узлов.

```json
// Response
{
    "nodes": [
        {
            "node_id": "node_001",
            "username": "operator1",
            "status": "online",
            "connected_at": "2024-01-15T10:00:00Z",
            "last_seen": "2024-01-15T10:05:00Z",
            "channels": ["N1", "N2", "N3", "N4", "N6"],
            "location": {
                "latitude": 55.7558,
                "longitude": 37.6173
            }
        },
        {
            "node_id": "node_002",
            "username": "operator2",
            "status": "online",
            "connected_at": "2024-01-15T10:01:00Z",
            "last_seen": "2024-01-15T10:05:00Z",
            "channels": ["N1", "N3", "N4", "N6"],
            "location": {
                "latitude": 55.7560,
                "longitude": 37.6180
            }
        }
    ],
    "total": 2
}
```

### POST /api/v1/network/targets/sync

Синхронизация целей.

```json
// Request
{
    "targets": [
        {
            "target_id": "tgt_001",
            "class_id": 0,
            "class_name": "beetle",
            "confidence": 0.95,
            "bounding_box": {"x": 120, "y": 80, "width": 60, "height": 90},
            "image_id": "img_001.jpg",
            "node_id": "node_001",
            "timestamp": 1705312800.0
        }
    ]
}

// Response
{
    "status": "synced",
    "synced_count": 1,
    "broadcast_to": ["node_002"]
}
```

### GET /api/v1/network/targets

Получение целей от других узлов.

```json
// Response
{
    "targets": [
        {
            "target_id": "tgt_001",
            "node_id": "node_002",
            "class_name": "beetle",
            "confidence": 0.92,
            "bounding_box": {"x": 200, "y": 150, "width": 50, "height": 80},
            "timestamp": 1705312800.0,
            "image_id": "img_005.jpg"
        }
    ],
    "total": 1,
    "nodes_with_targets": ["node_002"]
}
```

### POST /api/v1/network/chat/send

Отправка сообщения.

```json
// Request
{
    "text": "Обнаружена группа жуков в секторе B",
    "recipient": "operator2",
    "mentions": ["operator2"]
}

// Response
{
    "status": "sent",
    "message_id": "msg_20240115_001",
    "delivered_to": ["operator2"]
}
```

### GET /api/v1/network/chat/messages

История сообщений.

```json
// Response
{
    "messages": [
        {
            "message_id": "msg_001",
            "sender": "operator1",
            "text": "Начинаю сканирование сектора A",
            "timestamp": "2024-01-15T10:00:00Z"
        },
        {
            "message_id": "msg_002",
            "sender": "operator2",
            "text": "Принято, я в секторе B",
            "timestamp": "2024-01-15T10:01:00Z"
        }
    ],
    "total": 2
}
```

### POST /api/v1/network/files/upload

Загрузка файла.

```json
// Request (multipart/form-data)
{
    "file": "<binary_data>",
    "type": "image",
    "description": "Новое изображение для обработки"
}

// Response
{
    "status": "uploaded",
    "file_id": "file_20240115_001",
    "filename": "scene_001.jpg",
    "size_bytes": 5242880,
    "synced_to": ["node_002"],
    "download_url": "/api/v1/network/files/file_20240115_001/download"
}
```

### POST /api/v1/network/location/share

Обмен местоположением.

```json
// Request
{
    "latitude": 55.7558,
    "longitude": 37.6173,
    "altitude": 150.0,
    "heading": 180.0,
    "camera_fov": {"horizontal": 60.0, "vertical": 45.0}
}

// Response
{
    "status": "shared",
    "location_id": "loc_20240115_001",
    "broadcast_to": ["node_002"]
}
```

## Безопасность

### Рекомендации по безопасности

| Мера | Описание |
|------|----------|
| **TLS/SSL** | Шифрование WebSocket-соединений |
| **JWT ротация** | Регулярная смена secret key |
| **Rate limiting** | Ограничение запросов на узел |
| **IP whitelist** | Разрешённые IP-адреса |
| **Аудит логов** | Логирование всех сетевых операций |
| **Изоляция** | Сетевое разделение каналов |

### TLS-конфигурация

```yaml
# TLS конфигурация
tls:
  enabled: true
  cert_path: "/etc/ssl/certs/muravei.crt"
  key_path: "/etc/ssl/private/muravei.key"
  ca_path: "/etc/ssl/certs/ca.crt"
  verify_client: false    # true для mTLS
  
  # Цифры шифрования
  cipher_suites:
    - "TLS_AES_256_GCM_SHA384"
    - "TLS_CHACHA20_POLY1305_SHA256"
    - "TLS_AES_128_GCM_SHA256"
```

### IP-фильтрация

```yaml
# IP-фильтрация
security:
  ip_filtering:
    enabled: true
    mode: "whitelist"  # whitelist или blacklist
    
    whitelist:
      - "192.168.1.0/24"
      - "10.0.0.0/8"
      
    blacklist: []
    
  # Защита от DoS
  dos_protection:
    enabled: true
    max_connections_per_ip: 10
    max_messages_per_second: 60
    ban_duration_minutes: 30
```

## Рекомендации

1. **Используйте TLS** для всех сетевых соединений в production
2. **Регулярно меняйте JWT secret** (минимум раз в 30 дней)
3. **Мониторьте WebSocket-подключения** через N6 (Control Channel)
4. **Настройте rate limiting** для предотвращения перегрузки
5. **Используйте выделенную сеть** для передачи данных целей
6. **Резервируйте Hub-сервер** для отказоустойчивости
7. **Логгируйте все операции** для аудита и расследования инцидентов
