# MuraveiVision PRO — Unified Documentation

## Quick Start

- **[Operator Guide](01-OPERATOR/OVERVIEW.md)** — Field operations: detection, segmentation, batch scan
- **[Engineer Guide](02-ENGINEER/DEPLOYMENT.md)** — Installation, configuration, hardware setup
- **[Developer Guide](03-DEVELOPER/ARCHITECTURE.md)** — Architecture, API, testing, contributing

## Documentation Structure

```
docs/
├── 00-GETTING-STARTED/          # Quick start guides
├── 01-OPERATOR/                 # Field operations (operator role)
├── 02-ENGINEER/                 # Deployment & maintenance (engineer role)
├── 03-DEVELOPER/                # Development & testing (developer role)
├── 04-FEATURES/                 # Feature descriptions (all roles)
├── 05-REFERENCE/                # API, errors, config (all roles)
├── 06-SECURITY/                 # Security & air-gap policies
├── 07-RELEASES/                 # Release notes & changelog
├── GLOSSARY.md                  # Terminology glossary
├── INDEX.md                     # This file — unified navigation
└── legacy/                      # Archived documents
```

## Role-Based Navigation

### Operator (Полевая работа)
- Media workflow: loading, viewing, GPS sidecars
- Detection workflow: YOLO, SAHI, Inspector, Ollama
- Segmentation: YOLO-seg, SAM3 interactive & propagate
- Batch operations: Batch Scan, Batch Segmentation, Change Detection
- AI analysis: Rules, alerts, session trace
- Training: quick fine-tuning, checkpoint resume
- 3D reconstruction: COLMAP, DA3, GSplat, Flight3D
- Network sharing: target exchange, chat, location sharing

### Engineer (Развёртывание & Обслуживание)
- Deployment: dev setup, portable build, field deployment
- Configuration: SQLite settings, SAHI, validator, JWT
- Models: weights, import from USB, class catalog
- Hardware: GPU detection, VRAM tiers, CUDA/DirectML/AMD
- Network setup: hub+client, JWT, WebSocket N1-N6
- Maintenance: backups, updates, logging
- Diagnostics: session trace, YOLO debug, smoke tests

### Developer (Разработка)
- Architecture: components, data flow, state management
- API reference: all endpoints with curl examples
- Database: schema, migrations, WAL mode
- Testing: unit, E2E, smoke, field tests
- Contributing: git discipline, code review, air-gap constraints
- Debugging: Python, React, WebSocket, VRAM profiling

## Key Features

| Feature | Description | Docs |
|---------|-------------|------|
| **YOLO Detection** | YOLO26n-ft with SAHI slicing | [Detection](04-FEATURES/DETECTION.md) |
| **SAM3** | Interactive segmentation + propagate | [Segmentation](04-FEATURES/SEGMENTATION.md) |
| **DA3** | Depth Anything 3 dense reconstruction | [3D Recon](04-FEATURES/RECON_3D.md) |
| **Batch Scan** | Video scan by detections | [Batch Operations](04-FEATURES/BATCH_OPERATIONS.md) |
| **Change Detection** | Compare "before/after" | [Batch Operations](04-FEATURES/BATCH_OPERATIONS.md) |
| **Network v3.3** | Multi-machine target sync | [Network](04-FEATURES/NETWORK.md) |
| **HUD Exclusion** | Auto-blur objects | [Detection](04-FEATURES/DETECTION.md) |
| **Session Trace** | Session logging | [AI Analysis](01-OPERATOR/AI_ANALYSIS.md) |

## Security & Air-Gap

- **Air-gap enforced**: No runtime downloads from HuggingFace/PyPI/GitHub
- **P0 security**: RCE prevention (pickle→msgpack), SQL injection whitelist, path traversal validation
- **P1 security**: Prompt injection protection, filename sanitization, thread-safe DB
- **P2 security**: Prompt injection DATA section wrapping
- See [Security Audit](06-SECURITY/SECURITY_AUDIT.md) for full details

## Version Information

- **Current version**: v3.2.0 (2026-09-19)
- **Bug fixes**: 40 total (P0: 11, P1: 14, P2: 15)
- **New in v3.2.0**: DA3 Dense Backend (all 4 variants)
- See [v3.2.0 Release Notes](07-RELEASES/V3.2.0.md)

## Legacy Documentation

Older documents have been archived in [docs/legacy/](legacy/). These include:
- Master Plan, Roadmap, Known Issues
- Phase retrospectives (Phase 3, 4)
- Studio proposal, field specs
- Skill codex files
