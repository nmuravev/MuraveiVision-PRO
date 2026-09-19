# Platform Matrix — MuraveiVision PRO

## Supported Platforms

| Platform | Status | Notes |
|----------|--------|-------|
| **Windows (native)** | ✅ Supported | Primary platform. Portable ZIP + Запустить.bat. CUDA/CPU torch. |
| **Linux desktop** | ❌ Removed | Launcher scripts (.sh) removed from repo. Not part of Windows product. |
| **WSL runtime** | ❌ Not required | Project does not auto-start WSL/Docker. If WSL window appears, it's external (Docker Desktop, VS Code WSL extension). |
| **Docker** | ❌ Not required | No Dockerfile, docker-compose, or container runtime in project. |
| **Android** | 🔜 Future (v5.0) | Based on existing React frontend + FastAPI API. Not implemented yet. |
| **iOS** | ⏸️ Not planned | Unless operator decides later. |

## Windows Portable Packs

| Pack | Contents | Size Advisory |
|------|----------|---------------|
| **Mini** | YOLO + SAM3 + SAHI + CUDA torch + rasterio. NO DA3/AliceVision/gsplat. | warn>4.5 GB / reject>5 GB |
| **FullKit** | Mini + AliceVision + DA3 (4 weights) + gsplat + colmap. | no-DA3: warn>9.5 / reject>10 GB<br>+DA3: warn>18 / reject>22 GB |

## Linux/WSL/Docker Removal

- **Запустить.sh** — removed from repo (2026-09-19)
- **scripts/bootstrap_portable.sh** — removed from repo (2026-09-19)
- **sidecars/gsplat_examples/benchmarks/*.sh** — left in repo as examples, excluded from portable packs
- **build_portable.ps1** — no longer copies .sh, .desktop, systemd, ELF binaries
- **WSL/Docker auto-spawn** — not present in project code (confirmed 2026-09-19)

## Android Future (v5.0)

Android app will be based on:
- **React frontend** — existing `src/`, `dist/`, Vite build
- **FastAPI backend** — existing `backend/`, REST `/api/*`, WebSocket `/ws/*`
- **Auth layer** — cookie or token strategy (to be finalized)
- **Media tree, detections, timeline, network chat, AI status** — all preserved as API contracts

Android development:
- Not started. No Android code in repo.
- Platform adapter needed for paths/ffmpeg/sidecars.
- No Windows-only hardcoding in core services.
- See `docs/ANDROID_FUTURE.md` for details.
