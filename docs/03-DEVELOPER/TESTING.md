# Testing — MuraveiVision PRO

> **Стратегии тестирования: unit, integration, E2E, smoke, field tests.**

## Обзор

MuraveiVision PRO имеет комплексную систему тестирования с 4 уровнями: smoke, unit, integration, E2E.

## Test Structure

```
backend/tests/
├── conftest.py                 # Shared fixtures
├── smoke/                      # Smoke tests (quick health checks)
│   ├── test_health.py
│   ├── test_db.py
│   ├── test_gpu.py
│   └── test_model_load.py
├── unit/                       # Unit tests (isolated)
│   ├── test_detection_service.py
│   ├── test_segmentation_service.py
│   ├── test_batch_service.py
│   ├── test_session_service.py
│   └── test_utils/
├── integration/                # Integration tests
│   ├── test_detection_flow.py
│   ├── test_segmentation_flow.py
│   └── test_batch_flow.py
├── e2e/                        # End-to-end tests
│   ├── test_full_workflow.py
│   └── test_network_sync.py
└── load_test.py                # Load tests (ignored in CI)
```

## Running Tests

### Canonical Command

```bash
cd /d D:\LLM\MuraveiVision-PRO
set "PYTHONPATH=backend"
muravei_env\Scripts\python.exe -m pytest backend/tests/ -q --ignore=backend/tests/load_test.py
```

### Test Commands

```bash
# All tests (except load)
muravei_env\Scripts\python.exe -m pytest backend/tests/ -q --ignore=backend/tests/load_test.py

# Smoke tests only
muravei_env\Scripts\python.exe -m pytest backend/tests/smoke/ -q

# Unit tests only
muravei_env\Scripts\python.exe -m pytest backend/tests/unit/ -q

# Integration tests
muravei_env\Scripts\python.exe -m pytest backend/tests/integration/ -q

# E2E tests
muravei_env\Scripts\python.exe -m pytest backend/tests/e2e/ -q

# With coverage
muravei_env\Scripts\python.exe -m pytest backend/tests/ --cov=backend --cov-report=html -q

# Specific test file
muravei_env\Scripts\python.exe -m pytest backend/tests/smoke/test_health.py -v

# Specific test function
muravei_env\Scripts\python.exe -m pytest backend/tests/unit/test_detection.py::test_detect_single_image -v
```

## Smoke Tests

### Purpose

Быстрые проверки здоровья системы (< 10 seconds total).

### Test Suite

| Test | File | Time | Description |
|------|------|------|-------------|
| Health | `test_health.py` | 0.1s | Health endpoint responds |
| Database | `test_db.py` | 0.2s | Database writable |
| GPU | `test_gpu.py` | 0.5s | GPU available |
| Model Load | `test_model_load.py` | 2.0s | Model loads without error |
| Detection | `test_detection.py` | 1.0s | Single detection works |
| Frontend | `test_frontend.py` | 0.3s | Frontend accessible |

### Example: test_health.py

```python
import pytest
import httpx

@pytest.mark.smoke
@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health endpoint returns healthy status."""
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert data["version"] == "3.2.0"
```

### Example: test_gpu.py

```python
import pytest
import torch

@pytest.mark.smoke
def test_gpu_available():
    """Test GPU is available for inference."""
    assert torch.cuda.is_available(), "CUDA not available"
    
    gpu_name = torch.cuda.get_device_name(0)
    vram = torch.cuda.get_device_properties(0).total_mem / 1e9
    
    assert vram >= 4.0, f"VRAM too low: {vram:.1f} GB"
    print(f"GPU: {gpu_name}, VRAM: {vram:.1f} GB")
```

## Unit Tests

### Purpose

Тестирование отдельных функций и классов в изоляции.

### Test Categories

```
unit/
├── test_detection_service.py    # Detection logic
├── test_segmentation_service.py # Segmentation logic
├── test_batch_service.py        # Batch processing
├── test_session_service.py      # Session management
├── test_backup_service.py       # Backup logic
└── test_utils/
    ├── test_gpu.py              # GPU utilities
    ├── test_path.py             # Path validation
    ├── test_sql.py              # SQL builder
    └── test_crypto.py           # JWT, encryption
```

### Example: test_detection_service.py

```python
import pytest
from backend.services.detection_service import run_detection
from backend.models.yolo import YOLOModel

@pytest.mark.unit
@pytest.mark.asyncio
async def test_detect_single_image(tmp_path):
    """Test detection on single image."""
    # Create test image
    test_image = tmp_path / "test.jpg"
    test_image.write_bytes(b"fake_image_data")
    
    # Run detection
    result = await run_detection(
        image=test_image,
        model="yolo26s-ft",
        sahi_enabled=False
    )
    
    # Verify result
    assert result["status"] == "success"
    assert "detections" in result
    assert isinstance(result["detections"], list)
    assert result["processing_time_ms"] > 0

@pytest.mark.unit
@pytest.mark.asyncio
async def test_detect_with_sahi(tmp_path):
    """Test detection with SAHI slicing."""
    test_image = tmp_path / "test_large.jpg"
    test_image.write_bytes(b"fake_large_image")
    
    result = await run_detection(
        image=test_image,
        model="yolo26s-ft",
        sahi_enabled=True,
        slice_height=512,
        slice_width=512,
        overlap=0.2
    )
    
    assert result["status"] == "success"
    assert result["sahi_used"] is True
```

### Example: test_path.py

```python
import pytest
from backend.utils.path import safe_path
from pathlib import Path

@pytest.mark.unit
def test_safe_path_valid():
    """Test valid path is accepted."""
    base = Path("/data")
    user_path = "images/test.jpg"
    
    result = safe_path(base, user_path)
    assert result == Path("/data/images/test.jpg")

@pytest.mark.unit
def test_safe_path_traversal():
    """Test path traversal is blocked."""
    base = Path("/data")
    user_path = "../secret/config.yaml"
    
    with pytest.raises(ValueError, match="Path traversal detected"):
        safe_path(base, user_path)
```

## Integration Tests

### Purpose

Тестирование взаимодействия между компонентами.

### Test Suite

```
integration/
├── test_detection_flow.py       # Detection pipeline
├── test_segmentation_flow.py    # Segmentation pipeline
├── test_batch_flow.py           # Batch processing
└── test_session_flow.py         # Session lifecycle
```

### Example: test_detection_flow.py

```python
import pytest
from backend.services.detection_service import run_detection
from backend.services.session_service import create_session, save_detections

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_detection_flow(tmp_path):
    """Test complete detection flow with session."""
    # Create session
    session = await create_session(name="test_session")
    
    # Run detection
    test_image = tmp_path / "test.jpg"
    test_image.write_bytes(b"fake_image")
    
    result = await run_detection(
        image=test_image,
        model="yolo26s-ft",
        session_id=session["id"]
    )
    
    # Save detections
    await save_detections(session["id"], result["detections"])
    
    # Verify
    assert result["status"] == "success"
    assert len(result["detections"]) > 0
    
    # Check database
    from backend.database import get_detections
    db_detections = await get_detections(session["id"])
    assert len(db_detections) == len(result["detections"])
```

## E2E Tests

### Purpose

Полное тестирование пользовательских сценариев.

### Test Suite

```
e2e/
├── test_full_workflow.py        # Complete user workflow
└── test_network_sync.py         # Network synchronization
```

### Example: test_full_workflow.py

```python
import pytest
import httpx
from pathlib import Path

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_operator_workflow():
    """Test complete operator workflow."""
    base_url = "http://localhost:8000"
    
    # 1. Login
    login_resp = await client.post(f"{base_url}/api/auth/login", json={
        "username": "admin",
        "password": "test-password"
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Upload media
    with open("test_data/sample.jpg", "rb") as f:
        upload_resp = await client.post(
            f"{base_url}/api/media/upload",
            files={"file": ("sample.jpg", f, "image/jpeg")},
            headers=headers
        )
    assert upload_resp.status_code == 200
    
    # 3. Run detection
    detect_resp = await client.post(
        f"{base_url}/api/detect",
        data={"image": ("sample.jpg", open("test_data/sample.jpg", "rb"))},
        headers=headers
    )
    assert detect_resp.status_code == 200
    detections = detect_resp.json()["detections"]
    
    # 4. Run segmentation
    seg_resp = await client.post(
        f"{base_url}/api/segment/interactive",
        data={
            "image": ("sample.jpg", open("test_data/sample.jpg", "rb")),
            "tool": "point",
            "point_x": "250",
            "point_y": "180"
        },
        headers=headers
    )
    assert seg_resp.status_code == 200
    
    # 5. Export results
    export_resp = await client.post(
        f"{base_url}/api/detect/export",
        json={"format": "coco"},
        headers=headers
    )
    assert export_resp.status_code == 200
    
    # Verify all steps completed
    assert len(detections) > 0
    assert seg_resp.json()["status"] == "success"
```

## Test Fixtures

### conftest.py

```python
import pytest
import asyncio
import tempfile
from pathlib import Path

@pytest.fixture
def tmp_path(tmp_path):
    """Override default tmp_path fixture."""
    return tmp_path

@pytest.fixture
async def test_image(tmp_path):
    """Create a test image."""
    image_path = tmp_path / "test.jpg"
    # Create a simple test image
    from PIL import Image
    img = Image.new("RGB", (640, 480), color="red")
    img.save(image_path)
    return image_path

@pytest.fixture
def sample_detections():
    """Sample detection results."""
    return [
        {
            "class": "ant_worker",
            "confidence": 0.95,
            "bbox": [120, 45, 180, 95]
        },
        {
            "class": "cricket",
            "confidence": 0.87,
            "bbox": [340, 210, 380, 250]
        }
    ]

@pytest.fixture(scope="session")
def event_loop():
    """Create session-scoped event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

## Test Markers

| Marker | Description | When to use |
|--------|-------------|-------------|
| `@pytest.mark.smoke` | Quick health checks | CI every commit |
| `@pytest.mark.unit` | Unit tests | Local development |
| `@pytest.mark.integration` | Integration tests | Pre-merge |
| `@pytest.mark.e2e` | End-to-end tests | Release candidate |
| `@pytest.mark.load` | Load tests | Performance testing |
| `@pytest.mark.asyncio` | Async test | Async functions |

## CI Integration

### GitHub Actions

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: windows-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          python -m venv muravei_env
          muravei_env\Scripts\activate
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      
      - name: Run smoke tests
        run: |
          set "PYTHONPATH=backend"
          muravei_env\Scripts\python.exe -m pytest backend/tests/smoke/ -q
      
      - name: Run unit tests
        run: |
          set "PYTHONPATH=backend"
          muravei_env\Scripts\python.exe -m pytest backend/tests/unit/ -q
      
      - name: Run integration tests
        run: |
          set "PYTHONPATH=backend"
          muravei_env\Scripts\python.exe -m pytest backend/tests/integration/ -q
```

## Coverage

### Generating coverage

```bash
# HTML report
muravei_env\Scripts\python.exe -m pytest backend/tests/ \
  --cov=backend \
  --cov-report=html \
  --cov-report=term-missing \
  -q

# Output:
# Name                          Stmts   Miss  Cover
# -------------------------------------------------
# backend/main.py                 45      3    93%
# backend/api/detection.py        78      5    94%
# backend/services/detection_service.py  120     8    93%
# -------------------------------------------------
# TOTAL                           892     52    94%
```

### Coverage requirements

| Level | Minimum | Current |
|-------|---------|---------|
| **Smoke** | 100% | 100% |
| **Unit** | 80% | 93% |
| **Integration** | 70% | 88% |
| **Overall** | 85% | 94% |

## Troubleshooting

### Проблема: Тесты падают с ошибкой импорта

```
ModuleNotFoundError
Solution:
1. Проверьте PYTHONPATH: set "PYTHONPATH=backend"
2. Проверьте что venv активен
3. Проверьте что зависимости установлены
```

### Проблема: Асинхронные тесты таймятся

```
TimeoutError
Solution:
1. Увеличьте timeout: @pytest.mark.asyncio(timeout=30)
2. Проверьте что event loop запущен
3. Используйте fixture event_loop
```

## Дальнейшие шаги

1. **[Contributing](./CONTRIBUTING.md)** — guidelines для вклада
2. **[Debugging](./DEBUGGING.md)** — отладка
3. **[API Reference](./API_REFERENCE.md)** — API docs

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
