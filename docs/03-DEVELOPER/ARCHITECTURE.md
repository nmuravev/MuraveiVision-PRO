# Architecture — MuraveiVision PRO

> **Архитектура системы: компоненты, data flow, state management.**

## Обзор

MuraveiVision PRO — full-stack приложение с клиент-серверной архитектурой.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              React + TypeScript + Vite               │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐           │   │
│  │  │ Canvas   │ │ Panels   │ │ Modals   │           │   │
│  │  └──────────┘ └──────────┘ └──────────┘           │   │
│  │  ┌─────────────────────────────────────────────┐  │   │
│  │  │         Zustand State Management             │  │   │
│  │  └─────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / WebSocket
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ Detection│ │ Segment. │ │   AI     │ │ Network  │      │
│  │  API     │ │   API    │ │   API    │ │   API    │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              Services Layer                          │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐           │  │
│  │  │  YOLO    │ │   SAM3   │ │   DA3    │           │  │
│  │  │ Service  │ │ Service  │ │ Service  │           │  │
│  │  └──────────┘ └──────────┘ └──────────┘           │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              Database Layer                           │  │
│  │         SQLite (WAL mode, 8 tables)                  │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Backend Architecture

### Directory Structure

```
backend/
├── main.py                    # FastAPI app entry point
├── config.py                  # Configuration loader
├── database.py                # Database connection
├── api/                       # API routers
│   ├── __init__.py
│   ├── detection.py           # /api/detect*
│   ├── segmentation.py        # /api/segment*
│   ├── ai.py                  # /api/ai/*
│   ├── batch.py               # /api/batch*
│   ├── network.py             # /api/network/*
│   └── auth.py                # /api/auth/*
├── models/                    # ML model wrappers
│   ├── __init__.py
│   ├── yolo.py               # YOLO inference
│   ├── sam3.py               # SAM3 segmentation
│   ├── da3.py                # DA3 depth estimation
│   └── ollama.py             # Ollama LLM client
├── services/                  # Business logic
│   ├── __init__.py
│   ├── detection_service.py  # Detection orchestration
│   ├── segmentation_service.py
│   ├── batch_service.py
│   ├── session_service.py
│   ├── backup_service.py
│   └── network_service.py
├── schemas/                   # Pydantic models
│   ├── __init__.py
│   ├── detection.py
│   ├── segmentation.py
│   ├── session.py
│   └── network.py
├── utils/                     # Utilities
│   ├── __init__.py
│   ├── gpu.py                # GPU detection
│   ├── path.py               # Path validation
│   ├── sql.py                # SQL builder
│   └── crypto.py             # JWT, encryption
└── tests/                     # Test suite
    ├── conftest.py
    ├── smoke/
    ├── unit/
    ├── integration/
    └── e2e/
```

### API Layer

```
API Router Pattern:
┌─────────────────────────────────────────────┐
│  main.py (FastAPI)                          │
│  ┌───────────────────────────────────────┐  │
│  │ app = FastAPI()                       │  │
│  │ app.include_router(detection_router)  │  │
│  │ app.include_router(segmentation_router)│ │
│  └───────────────────────────────────────┘  │
│                                              │
│  api/detection.py                           │
│  ┌───────────────────────────────────────┐  │
│  │ router = APIRouter()                  │  │
│  │ @router.post("/detect")               │  │
│  │ async def detect(image: UploadFile):  │  │
│  │     result = await detection_service  │  │
│  │     return result                     │  │
│  └───────────────────────────────────────┘  │
│                                              │
│  services/detection_service.py              │
│  ┌───────────────────────────────────────┐  │
│  │ async def run_detection(image):       │  │
│  │     model = await load_model()        │  │
│  │     if sahi_enabled:                  │  │
│  │         tiles = sahi_slice(image)     │  │
│  │         results = model.predict(tiles)│  │
│  │         results = merge_results()     │  │
│  │     else:                            │  │
│  │         results = model.predict(image)│  │
│  │     return postprocess(results)       │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### Model Wrappers

```
Model Interface Pattern:
┌─────────────────────────────────────────────┐
│  base.py (abstract)                         │
│  ┌───────────────────────────────────────┐  │
│  │ class BaseModel(ABC):                 │  │
│  │     @abstractmethod                   │  │
│  │     async def predict(image):         │  │
│  │         ...                           │  │
│  │     @abstractmethod                   │  │
│  │     def get_info(self):               │  │
│  │         ...                           │  │
│  └───────────────────────────────────────┘  │
│                                              │
│  yolo.py                                     │
│  ┌───────────────────────────────────────┐  │
│  │ class YOLOModel(BaseModel):           │  │
│  │     def __init__(self, path):         │  │
│  │         self.model = YOLO(path)       │  │
│  │     async def predict(self, image):   │  │
│  │         results = self.model(image)   │  │
│  │         return self._parse(results)   │  │
│  └───────────────────────────────────────┘  │
│                                              │
│  sam3.py                                     │
│  ┌───────────────────────────────────────┐  │
│  │ class SAM3Model(BaseModel):           │  │
│  │     def __init__(self, path):         │  │
│  │         self.processor = ...          │  │
│  │     async def segment(self, image):   │  │
│  │         ...                           │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

## Frontend Architecture

### Directory Structure

```
MurVis/src/
├── main.tsx                    # Entry point
├── App.tsx                     # Root component
├── components/                 # React components
│   ├── common/                # Shared components
│   │   ├── Button.tsx
│   │   ├── Modal.tsx
│   │   └── Loading.tsx
│   ├── canvas/                # Canvas components
│   │   ├── Viewer.tsx         # Main viewer
│   │   ├── Overlay.tsx        # Detection overlay
│   │   └── Controls.tsx       # Zoom, pan
│   ├── panels/                # Side panels
│   │   ├── MediaPanel.tsx
│   │   ├── DetectionPanel.tsx
│   │   ├── SegmentationPanel.tsx
│   │   └── ResultsPanel.tsx
│   └── layout/                # Layout components
│       ├── Header.tsx
│       ├── Sidebar.tsx
│       └── MainLayout.tsx
├── store/                     # Zustand stores
│   ├── useMediaStore.ts       # Media state
│   ├── useDetectionStore.ts   # Detection state
│   ├── useViewerStore.ts      # Viewer state
│   ├── useBatchScanStore.ts   # Batch scan state
│   └── useNetworkStore.ts     # Network state
├── hooks/                     # Custom hooks
│   ├── useDetection.ts        # Detection hook
│   ├── useReconBuild.ts       # 3D reconstruction
│   └── useWebSocket.ts        # WebSocket hook
├── api/                       # API client
│   ├── client.ts              # Axios instance
│   ├── detection.ts           # Detection endpoints
│   └── network.ts             # Network endpoints
└── types/                     # TypeScript types
    ├── detection.ts
    ├── segmentation.ts
    └── network.ts
```

### State Management (Zustand)

```
Zustand Store Pattern:
┌─────────────────────────────────────────────┐
│  useViewerStore.ts                          │
│  ┌───────────────────────────────────────┐  │
│  │ interface ViewerState {               │  │
│  │   zoom: number;                       │  │
│  │   panX: number;                      │  │
│  │   panY: number;                      │  │
│  │   rotation: number;                   │  │
│  │   setZoom: (zoom: number) => void;    │  │
│  │   resetView: () => void;              │  │
│  │ }                                     │  │
│  │                                       │  │
│  │ export const useViewerStore =        │  │
│  │   create<ViewerState>((set) => ({     │  │
│  │     zoom: 1,                          │  │
│  │     panX: 0,                          │  │
│  │     panY: 0,                          │  │
│  │     rotation: 0,                      │  │
│  │     setZoom: (zoom) => set({ zoom }), │  │
│  │     resetView: () => set({           │  │
│  │       zoom: 1, panX: 0, panY: 0,     │  │
│  │       rotation: 0                     │  │
│  │     }),                               │  │
│  │   }));                                │  │
│  └───────────────────────────────────────┘  │
│                                              │
│  Usage in component:                        │
│  ┌───────────────────────────────────────┐  │
│  │ function Viewer() {                   │  │
│  │   const zoom = useViewerStore(         │  │
│  │     (s) => s.zoom                     │  │
│  │   );                                  │  │
│  │   const setZoom = useViewerStore(      │  │
│  │     (s) => s.setZoom                  │  │
│  │   );                                  │  │
│  │   return <canvas zoom={zoom} />;      │  │
│  │ }                                     │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

## Data Flow

```
Complete Data Flow:
┌─────────┐     ┌──────────┐     ┌──────────┐
│  User   │────→│ Frontend │────→│  API     │
│  Action │     │  React   │     │  Request │
└─────────┘     └──────────┘     └──────────┘
                                  │
                                  ▼
                            ┌──────────┐
                            │ Service  │
                            │  Layer   │
                            └────┬─────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │  YOLO    │ │   SAM3   │ │   DA3    │
              │  Model   │ │  Model   │ │  Model   │
              └────┬─────┘ └────┬─────┘ └────┬─────┘
                   │            │            │
                   ▼            ▼            ▼
              ┌─────────────────────────────────┐
              │      SQLite Database            │
              │   (WAL mode, 8 tables)          │
              └─────────────────────────────────┘
                   │
                   ▼
              ┌──────────┐
              │ Response │
              │  JSON    │
              └────┬─────┘
                   │
                   ▼
              ┌──────────┐
              │  Frontend│
              │  Update  │
              └────┬─────┘
                   │
                   ▼
              ┌──────────┐
              │  Canvas  │
              │  Render  │
              └──────────┘
```

## WebSocket Architecture

```
WebSocket Channels:
┌─────────────────────────────────────────────┐
│  WebSocket Server (:8765)                   │
│  ┌───────────────────────────────────────┐  │
│  │  Channel Router                       │  │
│  │  ┌─────────────────────────────────┐  │  │
│  │  │  N1: status      (bi-dir)      │  │  │
│  │  │  N2: detections    (C→H)       │  │  │
│  │  │  N3: segments      (C→H)       │  │  │
│  │  │  N4: chat          (bi-dir)    │  │  │
│  │  │  N5: files         (bi-dir)    │  │  │
│  │  │  N6: location      (bi-dir)    │  │  │
│  │  └─────────────────────────────────┘  │  │
│  └───────────────────────────────────────┘  │
│                                              │
│  Connection Management:                      │
│  • Heartbeat every 30s                       │
│  • Auto-reconnect with exponential backoff  │
│  • Message queuing during disconnect        │
│  • Channel subscription model               │
└─────────────────────────────────────────────┘
```

## Database Schema

```
Database Tables (SQLite):
┌─────────────────────────────────────────────┐
│  1. sessions              Session metadata  │
│  2. detections            Detection results │
│  3. segments              Segmentation masks│
│  4. models                Model registry    │
│  5. users                 User accounts     │
│  6. network_peers         Network nodes     │
│  7. chat_messages         Chat history      │
│  8. session_trace         Session events    │
└─────────────────────────────────────────────┘

Key relationships:
sessions 1──N detections
sessions 1──N segments
detections 1──N segments
users 1──N sessions
```

## Security Architecture

```
Security Layers:
┌─────────────────────────────────────────────┐
│  Layer 1: Input Validation                  │
│  • SQL whitelist                            │
│  • Path traversal prevention               │
│  • Filename sanitization                   │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│  Layer 2: Authentication (JWT)              │
│  • Token validation                         │
│  • Rate limiting                            │
│  • IP filtering                             │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│  Layer 3: Air-gap Enforcement               │
│  • No runtime downloads                    │
│  • Offline-only operation                  │
│  • No external API calls                   │
└─────────────────────────────────────────────┘
```

## Performance Architecture

```
Performance Optimizations:
┌─────────────────────────────────────────────┐
│  Backend:                                   │
│  • GPU acceleration (CUDA/DirectML)        │
│  • Batch processing                         │
│  • FP16 precision                           │
│  • SQLite WAL mode                          │
│  • Connection pooling                       │
│                                              │
│  Frontend:                                  │
│  • Virtual scrolling                        │
│  • Canvas rendering (not DOM)               │
│  • Memoization (React.memo)                 │
│  • Lazy loading                             │
│  • Debounced API calls                      │
│                                              │
│  Network:                                   │
│  • Message batching                         │
│  • Compression (gzip)                        │
│  • Delta updates                            │
│  • WebSocket multiplexing                   │
└─────────────────────────────────────────────┘
```

## Дальнейшие шаги

1. **[API Reference](./API_REFERENCE.md)** — все endpoints
2. **[Database](./DATABASE.md)** — schema и миграции
3. **[Testing](./TESTING.md)** — стратегии тестирования

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
