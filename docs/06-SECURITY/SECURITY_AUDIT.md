# Security Audit — MuraveiVision PRO

> **Полный аудит безопасности: P0/P1/P2 fixes.**

## Summary

- **Total fixes:** 40 (P0: 11, P1: 14, P2: 15)
- **RCE prevention:** pickle → msgpack
- **SQL injection:** whitelist queries
- **Prompt injection:** DATA wrapping

## PIN-код Security

### Хранение PIN

- PIN хранятся в `muravei.db` (таблица `pins`) в зашифрованном виде
- SHA256 hash + base64 encoding
- **Никогда не хранятся в plaintext**

### Стандартные PIN (factory defaults)

| Роль | PIN | Действие |
|------|-----|----------|
| `operator` | `1234567` | **Необходимо изменить!** |
| `engineer` | `0000000` | **Необходимо изменить!** |
| `master` | `0987907` | **Необходимо изменить!** |

### Рекомендации

1. **Измените PIN-коды** при первом развертывании
2. Используйте PIN длиной минимум 7 символов
3. Регулярно меняйте PIN-коды
4. Логгируйте все изменения PIN

### Brute-force protection

- Максимум 5 попыток перед блокировкой
- Блокировка на 120 секунд
- Atomic SQL UPDATE для предотвращения race conditions
- Retry logic при `database is locked`

## P0 Fixes (Critical)

11 critical fixes including RCE prevention, SQL injection, path traversal, auth bypass.

## P1 Fixes (High)

14 high-priority fixes including prompt injection, rate limiting, CORS hardening.

## P2 Fixes (Medium)

15 medium-priority fixes including cache TTL, stale state refs, WebSocket stabilization.

## Версия

- **Приложение:** v3.2.0
