# Authentication — MuraveiVision PRO

> **JWT аутентификация и авторизация.**

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
