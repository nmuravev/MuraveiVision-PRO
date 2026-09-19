# Debugging — MuraveiVision PRO

> **Отладка: Python, React, WebSocket, VRAM profiling.**

## Overview

MuraveiVision PRO provides comprehensive debugging tools for backend (Python/FastAPI), frontend (React/TypeScript), and GPU (CUDA) debugging.

## Python Debugging

### VS Code Debugging

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Backend",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/backend/main.py",
      "console": "integratedTerminal",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/backend"
      }
    },
    {
      "name": "Python: Tests",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/venv/Scripts/python.exe",
      "args": [
        "-m", "pytest",
        "-v",
        "${file}"
      ],
      "console": "integratedTerminal"
    }
  ]
}
```

### Debugging Steps

```python
# 1. Set breakpoint
def detect_image(image):
    breakpoint()  # ← Python 3.7+ debugger
    result = model.predict(image)
    return result

# 2. Run with debugger
muravei_env\Scripts\python.exe -m pdb backend/main.py

# 3. Debug commands
# n - Next
# s - Step into
# c - Continue
# p variable - Print variable
# l - List code
# q - Quit
```

### Logging for Debugging

```python
# config/custom.yaml
logging:
  level: "DEBUG"  # For debugging
  file: "data/logs/app.log"

# In code
import logging
logger = logging.getLogger(__name__)

async def detect_image(image):
    logger.debug(f"Detecting in image: {image.shape}")
    result = await model.predict(image)
    logger.debug(f"Found {len(result)} detections")
    return result
```

### Common Python Issues

```
Issue: ModuleNotFoundError
Solution:
1. Check venv: where python
2. Check PYTHONPATH: set PYTHONPATH=backend
3. Reinstall: pip install -r requirements.txt

Issue: CUDA out of memory
Solution:
1. Check VRAM: nvidia-smi
2. Reduce batch_size in config
3. Use smaller model (yolo26n)
4. Close other GPU apps

Issue: Database locked
Solution:
1. Check WAL mode: PRAGMA journal_mode;
2. Close other connections
3. Run: db_vacuum.py
```

## React Debugging

### React DevTools

```bash
# Install React DevTools extension in Chrome
# Available: Chrome Web Store

# Features:
# • Component tree view
# • Props and state inspection
# • Performance profiling
# • Redux/Zustand state inspection
```

### Debugging Zustand Stores

```typescript
// Enable middleware for debugging
import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

export const useDetectionStore = create<typeof detectionStore>()(
  devtools(
    persist(
      (set, get) => ({
        detections: [],
        addDetection: (detection) => set((state) => ({
          detections: [...state.detections, detection]
        })),
      }),
      { name: 'detection-storage' }
    )
  )
)

// Chrome DevTools → React → Zustand → useDetectionStore
```

### Frontend Debugging

```typescript
// Add debug logging
function ViewerComponent() {
  const [debugMode, setDebugMode] = useState(false);
  
  const handleDetection = async (data) => {
    if (debugMode) {
      console.log('Detection data:', data);
      console.table(data.detections);
    }
    
    // Process detection
    processDetections(data);
  };
  
  return (
    <div>
      <button onClick={() => setDebugMode(!debugMode)}>
        Debug: {debugMode ? 'ON' : 'OFF'}
      </button>
      <canvas onDetection={handleDetection} />
    </div>
  );
}
```

### Network Tab Debugging

```
Chrome DevTools → Network tab:

1. Filter by XHR/Fetch
2. Click request
3. View:
   • Headers (auth, content-type)
   • Payload (request body)
   • Response (API response)
   • Timing (request duration)
```

## WebSocket Debugging

### WebSocket Monitor

```python
# Enable WebSocket debug logging
# config/custom.yaml
logging:
  websocket: true
  log_file: "data/logs/websocket.log"
  log_level: "DEBUG"
```

### WebSocket Debug Script

```bash
# Test WebSocket connection
muravei_env\Scripts\python.exe backend/scripts/ws_test.py \
  --url ws://localhost:8765 \
  --channels status,detections \
  --duration 30

# Output:
# [10:00:00] Connecting to ws://localhost:8765
# [10:00:01] Connected
# [10:00:01] Subscribed to: status, detections
# [10:00:05] Received: status {"connected_clients": 3}
# [10:00:10] Received: detections {...}
# [10:00:30] Test complete: 15 messages received
```

### Frontend WebSocket Debug

```typescript
// Enhanced WebSocket hook with debugging
function useWebSocket(url: string, debug = false) {
  const [messages, setMessages] = useState<any[]>([]);
  
  useEffect(() => {
    const ws = new WebSocket(url);
    
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      
      if (debug) {
        console.log('[WS Received]', message.channel, message);
      }
      
      setMessages(prev => [...prev, message]);
    };
    
    ws.onerror = (error) => {
      console.error('[WS Error]', error);
    };
    
    ws.onclose = () => {
      console.log('[WS Closed]');
    };
    
    return () => ws.close();
  }, [url]);
  
  return { messages, send: (data) => ws.send(JSON.stringify(data)) };
}
```

## GPU Debugging

### VRAM Profiling

```python
# GPU memory profiler
import torch

def profile_gpu():
    """Profile GPU memory usage."""
    print("=" * 50)
    print("GPU Memory Profile")
    print("=" * 50)
    
    # Current usage
    allocated = torch.cuda.memory_allocated() / 1e9
    reserved = torch.cuda.memory_reserved() / 1e9
    total = torch.cuda.get_device_properties(0).total_mem / 1e9
    
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"Total VRAM: {total:.1f} GB")
    print(f"Reserved: {reserved:.1f} GB ({reserved/total*100:.0f}%)")
    print(f"Allocated: {allocated:.1f} GB ({allocated/total*100:.0f}%)")
    print(f"Free: {total - reserved:.1f} GB")
    print("=" * 50)
    
    return {
        "total": total,
        "reserved": reserved,
        "allocated": allocated,
        "free": total - reserved
    }

# Usage
profile_gpu()
```

### CUDA Debugging

```bash
# Check CUDA installation
muravei_env\Scripts\python.exe -c "
import torch
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'CUDA version: {torch.version.cuda}')
print(f'cuDNN version: {torch.backends.cudnn.version()}')
print(f'GPU: {torch.cuda.get_device_name(0)}')
"

# Check for CUDA errors
export CUDA_LAUNCH_BLOCKING=1
python backend/main.py
```

### GPU Diagnostics Script

```bash
muravei_env\Scripts\python.exe backend/scripts/gpu_diagnostics.py

# Output:
# ========================================
# GPU Diagnostics
# ========================================
# [OK] CUDA available: True
# [OK] CUDA version: 12.4
# [OK] Driver: 551.86
# [OK] GPU: NVIDIA GeForce RTX 4070
# [OK] VRAM: 8.0 GB
# [OK] Free VRAM: 5.9 GB
# [OK] Temperature: 52°C
# [OK] Utilization: 5%
# [OK] AVX2: supported
# ========================================
```

## Performance Profiling

### Python Profiler

```bash
# Line-by-line profiling
muravei_env\Scripts\python.exe -m cProfile -o profile.prof \
  backend/main.py

# View results
muravei_env\Scripts\python.exe -m pstats profile.prof
# > sort time
# > stats 10
```

### Memory Profiler

```bash
# Install memory profiler
pip install memory_profiler

# Profile specific function
@profile
def detect_image(image):
    result = model.predict(image)
    return result

# Run
python -m memory_profiler backend/main.py
```

### Frontend Performance

```
Chrome DevTools → Performance tab:

1. Click record
2. Perform actions (detection, segmentation)
3. Stop recording
4. Analyze:
   • FPS
   • Frame time
   • Scripting time
   • Rendering time
```

## Log Analysis

### Log Files

| File | Path | Purpose |
|------|------|---------|
| App log | `data/logs/app.log` | Main application |
| WebSocket log | `data/logs/websocket.log` | WS events |
| Error log | `data/logs/error.log` | Errors only |
| Access log | `data/logs/access.log` | HTTP requests |

### Searching Logs

```bash
# Search for errors
findstr /C:"ERROR" data\logs\app.log

# Search for specific pattern
findstr /C:"detection" data\logs\app.log

# View recent errors
powershell -Command "Get-Content data\logs\app.log -Tail 100 | Select-String 'ERROR'"
```

### Log Levels

| Level | When to Use |
|-------|-------------|
| DEBUG | Detailed debugging |
| INFO | Normal operation |
| WARNING | Something unexpected |
| ERROR | Functionality broken |
| CRITICAL | System unusable |

## Debug Checklist

```
Debugging Checklist:
┌─────────────────────────────────────────┐
│ Backend:                                │
│ ☐ Check logs: data/logs/app.log        │
│ ☐ Verify GPU: nvidia-smi               │
│ ☐ Check database: db_check.py          │
│ ☐ Test API endpoint manually           │
│ ☐ Enable debug logging                 │
│                                         │
│ Frontend:                               │
│ ☐ Check console: F12 → Console         │
│ ☐ Check network: F12 → Network         │
│ ☐ Check React DevTools                 │
│ ☐ Clear browser cache                  │
│ ☐ Try incognito mode                   │
│                                         │
│ WebSocket:                              │
│ ☐ Test connection: ws_test.py          │
│ ☐ Check channels subscribed            │
│ ☐ Verify message format                │
│ ☐ Check for reconnections              │
│                                         │
│ GPU:                                    │
│ ☐ Check VRAM: nvidia-smi               │
│ ☐ Check temperature                    │
│ ☐ Check CUDA version                   │
│ ☐ Profile memory usage                 │
└─────────────────────────────────────────┘
```

## Emergency Procedures

### Backend Won't Start

```bash
# 1. Check logs
type data\logs\error.log

# 2. Check dependencies
pip check

# 3. Check database
muravei_env\Scripts\python.exe backend/scripts/db_check.py

# 4. Reset database
muravei_env\Scripts\python.exe backend/scripts/init_db.py

# 5. Try CPU mode
# Edit config: gpu.device = "cpu"
```

### Frontend Won't Load

```bash
# 1. Check backend is running
curl http://localhost:8000/health

# 2. Clear frontend cache
cd MurVis
rm -rf node_modules
npm install
npm run build

# 3. Check CORS settings
# Verify config/custom.yaml CORS origins
```

## Дальнейшие шаги

1. **[API Reference](./API_REFERENCE.md)** — API docs
2. **[Testing](./TESTING.md)** — test strategies
3. **[Contributing](./CONTRIBUTING.md)** — contribution guidelines

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
