# Field machine: MacBook Pro (Intel) + Windows Boot Camp + AMD Radeon Pro 5500M

Целевая полевая конфигурация **без NVIDIA CUDA**. Цель — выжать максимум из Intel CPU + AMD Radeon (RDNA1) через CPU-бюджеты и DirectML (DX12) для YOLO.

## Hardware matrix

| Компонент | Значение | Примечание |
|-----------|----------|------------|
| CPU | Intel (MacBook Pro) | Boot Camp Windows |
| GPU | AMD Radeon Pro 5500M (RDNA1) | ~4 GB VRAM (система ~16 GB RAM) |
| CUDA | **нет** | torch.cuda.is_available() → False |
| ROCm | **нет** на Windows RDNA1 | не использовать |
| DX12 / DirectML | да | единственный GPU-путь для YOLO |

## Tracks

### Track A — Native Windows (рекомендуется для PAK)

1. Распаковать репозиторий + `muravei_env_pack_win_cpu.zip` в корень.
2. `scripts\setup_env.bat` → CPU torch + `onnxruntime-directml`.
3. `Запустить.bat`.
4. Профиль CPU применяется автоматически (`accelerator_kind()=="cpu"`).
5. YOLO: пресет / `yolo_inference_backend=directml` или `auto` → DirectML при наличии EP.

### Track B — WSL2 (опционально)

- Клонировать проект в `~/...` (**не** `/mnt/c/...` — I/O убьёт COLMAP).
- CUDA в WSL2 на AMD **нет**; смысл — Linux tooling / сборка, не ускорение GPU.
- Для детекции на AMD остаётся Track A (DirectML).

### Track C — Portable FullKit CPU

```powershell
.\scripts\build_portable.ps1 -FetchEmbeddablePython -FullKit -TorchFlavor cpu
# → portable\MuraveiVision_PRO_FullKit_win_cpu.zip
```

Не класть CUDA torch на AMD-ноут: лишний объём и путаница.

## Что ускоряется / что на CPU

| Подсистема | Ускорение на AMD 5500M | Ожидание |
|------------|------------------------|----------|
| YOLO detect | DirectML (experimental) | быстрее CPU; fallback на CPU при любой ошибке |
| COLMAP SfM | CPU only | десятки мин–часы на 9‑мин клипе; budgets 1200px / ~250 кадров |
| AliceVision Dense/Mesh | по умолчанию **отключено** | нет CUDA; `MURAVEI_CPU_DISABLE_DENSE=1` |
| gsplat | **отключено** | «требуется NVIDIA CUDA» |
| Torch train | CPU | медленно; не полевой сценарий |

## Acceptance criteria

1. На машине без CUDA: баннер «Нет NVIDIA GPU — режим CPU + DirectML (если доступен)»; Session Trace пишет `accelerator profile: cpu`.
2. COLMAP: `use_gpu=0`, `max_image_size≈1200`, `max_frames≈250` (env override допустим).
3. Dense/Mesh/Splat disabled с RU-причинами; Dense ETA hint «CPU: 1–3 часа».
4. DirectML YOLO: при `onnxruntime-directml` и `DmlExecutionProvider` — badge `YOLO: DirectML`; ошибка → logged fallback `YOLO: CPU`, без краша.
5. На NVIDIA-dev: `accelerator_kind=cuda`, CPU-баннер **не** показывается; CUDA YOLO path не ломается.
6. Пак `muravei_env_pack_win_cpu.zip` ≪ `win_cuda` (~1 GB vs ~3 GB).

## Env knobs

| Env | Meaning |
|-----|---------|
| `MURAVEI_FORCE_ACCELERATOR=cpu\|cuda` | smoke / тесты |
| `MURAVEI_CPU_DISABLE_DENSE=0\|1` | Dense/Mesh на CPU (default 1 = off) |
| `MURAVEI_CPU_DENSE_MAX_FRAMES` | cap кадров AV (default 100) |
| `MURAVEI_YOLO_BACKEND` / detect-config `yolo_inference_backend` | `auto\|torch\|directml` |
| `COLMAP_MAX_IMAGE_SIZE` / `COLMAP_MAX_FRAMES` / `COLMAP_USE_GPU` | ручные overrides |

См. [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md), [KNOWN_ISSUES.md](KNOWN_ISSUES.md).
