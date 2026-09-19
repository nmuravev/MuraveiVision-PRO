# Android Future — MuraveiVision PRO

## Overview

Android application is a future target, tentatively around version 5.0.
It will be based on the existing React frontend + FastAPI backend architecture.

## Architecture

### Shell Options (to be decided)
- **Capacitor** — wrap React web app as native Android APK
- **WebView** — custom Android activity hosting webview
- **PWA** — progressive web app (no native wrapper)
- **React Native** — later phase, if native performance needed

### Required API Contracts (MUST PRESERVE)

These endpoints and contracts form the Android foundation:

| Contract | Endpoint/Route | Description |
|----------|---------------|-------------|
| Auth | `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout` | Session/token management |
| Media | `GET /api/media/tree` | File/folder hierarchy |
| Detections | `GET /api/detections/classes`, `GET /api/detect/status` | Class dictionary, detection status |
| AI | `GET /api/ai/ollama/status` | Ollama availability |
| Network | `GET /api/network/config`, `GET /api/network/messages/unread` | Peer network config, chat |
| Recording | `GET /api/rec/status` | Recording status |
| System | `GET /api/system/hardware` | Hardware profile |
| WebSocket | `/ws/chat`, `/ws/detect` | Real-time chat, detection events |

### Frontend Components (MUST PRESERVE)

These React components form the UI foundation:
- `src/App.tsx` — main app shell
- `src/components/TopBar.tsx` — navigation bar
- `src/components/panels/*` — all panel components (Viewer, MediaPool, Inspector, etc.)
- `src/store/useMuraveiStore.ts` — global state
- `src/store/useViewerStore.ts` — viewer state
- `src/lib/aiVision.ts` — AI/OLLAMA integration
- `src/debug/sessionTrace.ts` — session tracing

### Platform Adapter Requirements

For Android compatibility:

1. **File paths** — abstracted via `BASE_DIR` from `config.py`, not hardcoded Windows paths
2. **FFmpeg** — Android needs separate binary (not bundled yet)
3. **Sidecars** — AliceVision/Colmap/DA3 not available on Android (feature-gated)
4. **WebSocket** — base URL configurable via env/config
5. **Auth** — cookie or token strategy must work in Android WebView/Capacitor

### Forbidden Changes (Android Guardrails)

The following MUST NOT be removed or broken without operator approve:
- `dist/` build output
- `package.json` build scripts (`build`, `dev`, `preview`)
- FastAPI backend routes (`/api/*`, `/ws/*`)
- Auth endpoints and dependencies
- Media tree, detections, timeline, network chat, AI status APIs
- WebSocket route handlers
- React frontend components referenced in build

### Development Notes

- No Android code will be added until operator requests it
- Current focus: Windows portable builds (v3.x)
- Android target: v5.0 (tentative)
- Web reference architecture: OpenReel (React + FastAPI + REST/WebSocket)
