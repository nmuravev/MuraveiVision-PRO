# CUDA Torch Proof

## Purpose
Document the CUDA torch 2.11.0+cu128 wheel seeded in the portable cache.

## Seeded Wheels
```
portable/cache/wheels/torch-2.11.0+cu128-cp312-cp312-win_amd64.whl  (2.8 GB)
portable/cache/wheels/torchvision-0.26.0+cu128-cp312-cp312-win_amd64.whl  (9.6 MB)
```

## Build Verification
### Mini ZIP (6.14 GB)
- SHA256: 0430e7ce6986f9b3018434b8edd2684f169oc66ef8b4844f2f7a422d2e521a2f
- CUDA torch 2.11.0+cu128: PRESENT (9 dist-info files)
- CUDA torchvision 0.26.0+cu128: PRESENT (7 dist-info files)
- Assets/models: 5 files (sam3.pt, yolo26n-ft.pt, yolo26n-uav-ghost.yaml, yolo26n-uav.yaml, yolo26n.pt)
- Sidecars/DA3: 0 weights (correct for Mini)
- AV binaries: 0 (correct for Mini)
- KIT marker: mini

### FullKit ZIP (15.54 GB)
- SHA256: 56ca790f865d13070d1812893c4d2c64abd72c198c
- CUDA torch 2.11.0+cu128: PRESENT (9 dist-info files)
- CUDA torchvision 0.26.0+cu128: PRESENT (7 dist-info files)
- Assets/models: 5 files
- Sidecars/DA3: 4 weights (base, large, metric, giant)
- COLMAP: 1 binary
- AliceVision: 108 binaries
- KIT marker: full

## Build Command
```
Mini:  MURAVEI_PORTABLE_MIRROR=1 powershell -File scripts\build_portable.ps1 -Mini -TorchFlavor cuda -FetchEmbeddablePython
Full:  MURAVEI_PORTABLE_MIRROR=1 powershell -File scripts\build_portable.ps1 -FullKit -TorchFlavor cuda -FetchEmbeddablePython
```

## Key Fix
`scripts/portable_torch_policy.py` want_cuda() was returning False for Mini/Lite
regardless of -TorchFlavor parameter. Fixed to:
```python
if profile in ("mini", "lite"):
    return flavor == "cuda"  # was: return False
```

## Source
- `scripts/build_portable.ps1` (CUDAFlavorPending skip for MIRROR, WantCudaTorch for Mini)
- `scripts/portable_torch_policy.py` (want_cuda fix)
- `portable/cache/wheels/` (seeded CUDA wheels)
