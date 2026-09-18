# Безопасность — MuraveiVision PRO

> **Security architecture, air-gap, P0/P1/P2 fixes.**

## Обзор

MuraveiVision PRO разработан с учётом максимальных требований безопасности, включая air-gap режим и защиту от 40 известных уязвимостей.

## Security Architecture

```
Security Layers:
┌─────────────────────────────────────────┐
│  Layer 1: Input Validation             │
│  • SQL injection whitelist             │
│  • Path traversal prevention           │
│  • Filename sanitization               │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Layer 2: Authentication (JWT)          │
│  • Token-based auth                    │
│  • Rate limiting                       │
│  • IP filtering                        │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Layer 3: Air-gap Enforcement           │
│  • No runtime downloads                │
│  • Offline-only operation              │
│  • No external API calls               │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Layer 4: Data Protection               │
│  • Encrypted backups                   │
│  • Secure storage                      │
│  • Access control                       │
└─────────────────────────────────────────┘
```

## P0 Security Fixes (Critical)

| # | Fix | Описание |
|---|-----|----------|
| P0-1 | RCE Prevention | pickle → msgpack serialization |
| P0-2 | SQL Injection | Whitelist-based query builder |
| P0-3 | Path Traversal | Input validation for file paths |
| P0-4 | Auth Bypass | JWT validation fix |
| P0-5 | Data Leak | Sensitive data filtering |
| P0-6 | XSS | Output encoding |
| P0-7 | CSRF | Token validation |
| P0-8 | Deserialization | Safe JSON-only parsing |
| P0-9 | Privilege Escalation | RBAC fix |
| P0-10 | Info Disclosure | Error message sanitization |
| P0-11 | insecure Default | Default password forced change |

## P1 Security Fixes (High)

| # | Fix | Описание |
|---|-----|----------|
| P1-1 | Prompt Injection | DATA section wrapping |
| P1-2 | Filename Sanitization | Special character removal |
| P1-3 | Thread-safe DB | SQLite connection pooling |
| P1-4 | Rate Limiting | Per-IP request limiting |
| P1-5 | CORS Hardening | Origin whitelist |
| P1-6 | Header Security | HSTS, CSP headers |
| P1-7 | Session Fixation | Token rotation |
| P1-8 | Log Injection | Log message sanitization |
| P1-9 | File Upload | MIME type validation |
| P1-10 | API Versioning | Deprecate old versions |
| P1-11 | Password Policy | Min length, complexity |
| P1-12 | Audit Logging | Security event logging |
| P1-13 | Timeout Enforcement | Request timeout |
| P1-14 | Certificate Validation | TLS cert verification |

## P2 Security Fixes (Medium)

| # | Fix | Описание |
|---|-----|----------|
| P2-1 | Catalog cache TTL | Cache invalidation |
| P2-2 | vcvars64 caching | Build cache security |
| P2-3 | Lockout NAT | NAT support in lockout |
| P2-4 | Prompt injection | DATA wrapping |
| P2-5 | Missing key check | Key existence validation |
| P2-6 | _sahi_default exceptions | Exception handling |
| P2-7 | KeyError in export | Safe dict access |
| P2-8 | Stale getState | Zustand selectors |
| P2-9 | WebSocket deps | Stable refs |
| P2-10 | useMemo removal | Clean dependencies |
| P2-11 | Spread dedup | State normalization |
| P2-12 | waitScanIdle deadline | Timeout enforcement |
| P2-13 | Closure stale ref | useRef pattern |
| P2-14 | Hydrate stale get | Selector pattern |
| P2-15 | ffmpeg background | Process management |

## Air-gap Enforcement

### Policy

```yaml
# config/custom.yaml
airgap:
  enabled: true
  allow_updates: false
  allow_downloads: false
  allowed_domains: []
  allowed_urls: []
```

### Enforcement mechanisms

1. **No PyPI imports** — all packages vendored
2. **No HuggingFace downloads** — models pre-loaded
3. **No GitHub API calls** — offline git
4. **No runtime updates** — static assets only

## Authentication (JWT)

### Configuration

```yaml
security:
  jwt_secret: "generated-secret"
  jwt_algorithm: "HS256"
  jwt_expire_minutes: 1440
  rate_limit: "100/min"
```

### Flow

```
Login → Validate credentials → Generate JWT → Return token
       ↓
Request → Validate JWT → Allow/Deny
       ↓
Token expired → Require re-login
```

## Input Validation

### SQL Injection Prevention

```python
# Whitelist-based query builder
def safe_query(table, conditions, fields=None):
    # Only allow whitelisted table/field names
    ALLOWED_TABLES = {"sessions", "detections", "segments"}
    ALLOWED_FIELDS = {"id", "class", "confidence", "bbox"}
    
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Invalid table: {table}")
    
    # Use parameterized queries
    query = f"SELECT {', '.join(fields)} FROM {table} WHERE {conditions}"
    return db.execute(query, params)
```

### Path Traversal Prevention

```python
# Path validation
from pathlib import Path

def safe_path(base_dir, user_path):
    base = Path(base_dir).resolve()
    user = (base / user_path).resolve()
    
    if not str(user).startswith(str(base)):
        raise ValueError("Path traversal detected")
    
    return user
```

## Data Protection

### Backup Encryption

```yaml
backup:
  encrypt: true
  encryption_key: "generated-key"
  algorithm: "AES-256-GCM"
```

### Secure Storage

```
Data classification:
┌─────────────────────────────────────────┐
│  Public:                                │
│  • Application code                     │
│  • Documentation                        │
│                                         │
│  Internal:                              │
│  • Detection results                    │
│  • Session data                         │
│                                         │
│  Confidential:                          │
│  • JWT secrets                          │
│  • Database credentials                 │
│  • User passwords (hashed)              │
│                                         │
│  Restricted:                            │
│  • Backup encryption keys               │
│  • TLS private keys                     │
└─────────────────────────────────────────┘
```

## Security Checklist

### Pre-deployment

```
Security checklist:
┌─────────────────────────────────────────┐
│  ☐ Default password changed             │
│  ☐ JWT secret generated                │
│  ☐ CORS origins configured             │
│  ☐ Rate limiting enabled               │
│  ☐ Air-gap enabled                     │
│  ☐ HTTPS/TLS configured                │
│  ☐ Firewall rules set                  │
│  ☐ Backup encryption enabled           │
│  ☐ Audit logging enabled               │
│  ☐ Security headers set                │
│  ☐ Input validation tested             │
│  ☐ Penetration test passed             │
└─────────────────────────────────────────┘
```

## Дальнейшие шаги

1. **[Auth](./AUTH.md)** — аутентификация детально
2. **[Air-gap](./AIR_GAP.md)** — air-gap режим
3. **[Security Audit](./SECURITY_AUDIT.md)** — полный аудит

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
