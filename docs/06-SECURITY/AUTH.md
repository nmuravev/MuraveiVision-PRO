# Authentication — MuraveiVision PRO

> **JWT аутентификация, PIN-коды ролей и авторизация.

## PIN-коды ролей

Система авторизации использует PIN-коды для трёх ролей. PIN хранятся в БД (`muravei.db`, таблица `pins`) в зашифрованном виде (SHA256 + base64).

### Стандартные PIN-коды

| Роль | PIN | Описание |
|------|-----|----------|
| `operator` | `1234567` | Оператор |
| `engineer` | `0000000` | Инженер |
| `master` | `0987907` | Мастер |

### Проверка PIN

```python
from services.db import find_role_by_pin, get_pin_role

# Найти роль по PIN
role = find_role_by_pin("1234567")  # "operator"

# Получить PIN по роли
pin_row = get_pin_role("operator")
# {"role": "operator", "pin_sha256": "...", "pin_b64": "...", "updated_at": ...}
```

### Обновление PIN

```python
from services.db import update_pin

# Обновить PIN для роли
update_pin("operator", "new_secure_pin")
```

### Защита от брутфорса

Система блокирует клиент после 5 неудачных попыток на 120 секунд.

```python
from services.db import record_failed_login, clear_lockout

# Record failed attempt (atomic)
result = record_failed_login("192.168.1.100")
# {"fail_count": 3, "locked_until": 0.0}

# Снять блокировку
clear_lockout("192.168.1.100")
```

## JWT Flow

```
Login → Validate → Generate Token → Return
       ↓
Request → Validate Token → Allow/Deny
       ↓
Expired → Require Re-login
```

## Configuration

```yaml
security:
  jwt_secret: "generated-secret"
  jwt_algorithm: "HS256"
  jwt_expire_minutes: 1440
  rate_limit: "100/min"
```

## Roles

| Role | Permissions |
|------|-------------|
| operator | View, detect, segment |
| engineer | All operator + config |
| admin | All + user management |

## Версия

- **Приложение:** v3.2.0
