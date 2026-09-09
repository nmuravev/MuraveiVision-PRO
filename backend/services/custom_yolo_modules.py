"""Custom YOLO modules for UAV-optimized MuraveiVision-PRO detection.

Phase 1: S2DConv — Space-to-Depth downsampling replacing stride-2 Conv in layer 0.
         Preserves 100% spatial information at first downsampling step.
         Weight transfer: 99.98% of YOLO26n pretrained weights remain compatible.

Phase 2: FasterGhostC3k2 — Ghost-lightweight C3k2 for neck VRAM reduction.
         Replaces C3k2 in layers 13, 16, 19 only (layer 22 with attn untouched).

These modules are registered into ultralytics.nn.tasks globals so parse_model()
can resolve them from YAML config without patching the pip package.
"""
from __future__ import annotations

import torch
import torch.nn as nn

from ultralytics.nn.modules.conv import Conv
from ultralytics.nn.modules.block import C2f


class SpaceToDepth(nn.Module):
    """Lossless spatial-to-channel rearrangement (pixel unshuffle).

    [B, C, H, W] -> [B, C*block_size^2, H/block_size, W/block_size]
    Exchanges spatial resolution for channel depth without discarding any information.
    """

    def __init__(self, block_size: int = 2):
        super().__init__()
        self.bs = block_size

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        N, C, H, W = x.size()
        bs = self.bs
        # Pad if not divisible (SAHI tiles can have odd dimensions)
        if H % bs != 0 or W % bs != 0:
            pad_h = (bs - H % bs) % bs
            pad_w = (bs - W % bs) % bs
            x = torch.nn.functional.pad(x, (0, pad_w, 0, pad_h))
            N, C, H, W = x.size()
        x = x.view(N, C, H // bs, bs, W // bs, bs)
        x = x.permute(0, 1, 3, 5, 2, 4).contiguous()
        return x.view(N, C * bs * bs, H // bs, W // bs)


class S2DConv(nn.Module):
    """Space-to-Depth + PWConv downsampling module.

    Replaces Conv(k=3, s=2) in the first backbone layer (3 -> C_out channels).
    S2D rearranges pixels into channels [3 -> 12], then PWConv projects to C_out.
    No spatial information is lost at the most critical downsampling step.

    YOLO26n layer 0 original: Conv(3, 16, k=3, s=2)  -> 497 params
    S2DConv replacement:       S2D(3->12) + Conv(12, 16, k=1) -> ~200 params
    """

    def __init__(self, c1: int, c2: int, k: int = 1, s: int = 1, p: int | None = None, g: int = 1, act: bool = True):
        super().__init__()
        self.s2d = SpaceToDepth(block_size=2)
        # After S2D: c1*4 channels, spatial H/2 x W/2
        self.conv = Conv(c1 * 4, c2, k=k, s=s, p=p, g=g, act=act)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(self.s2d(x))


class FasterGhostConv(nn.Module):
    """Lightweight convolution using standard conv (not DWConv) for cheap branch.

    Replaces Conv in neck to reduce VRAM while being faster than
    DWConv-based GhostConv on desktop/server GPUs.

    Based on EUAVDet FGM: primary PWConv compresses channels,
    standard Conv continues learning, outputs are concatenated.
    """

    def __init__(self, c1: int, c2: int, k: int = 1, s: int = 1, g: int = 1, act: bool = True):
        super().__init__()
        mid = c2 // 2
        # Primary: PWConv compresses input channels to hidden
        self.primary = Conv(c1, mid, k=1, s=s, g=g, act=act)
        # Cheap: standard 3x3 conv (NOT depthwise — faster on GPU)
        self.cheap = Conv(mid, mid, k=3, s=1, p=1, g=1, act=act)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x1 = self.primary(x)
        x2 = self.cheap(x1)
        return torch.cat([x1, x2], dim=1)


class FasterGhostBottleneck(nn.Module):
    """Ghost bottleneck: 1×1 PW projection + FasterGhostConv 3×3.

    Replaces standard Bottleneck(3×3 + 3×3) inside C3k2 neck blocks.
    ~55% parameter reduction per bottleneck vs standard.
    """

    def __init__(self, c1: int, c2: int, shortcut: bool = True, g: int = 1, e: float = 1.0):
        super().__init__()
        c_ = int(c2 * e)
        self.cv1 = Conv(c1, c_, 1, 1)
        self.cv2 = FasterGhostConv(c_, c2, 3, 1, g=g)
        self.add = shortcut and c1 == c2

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.cv2(self.cv1(x)) if self.add else self.cv2(self.cv1(x))


class FasterGhostC3k2(C2f):
    """Ghost-lightweight C3k2 for Neck VRAM reduction.

    Extends C2f (like C3k2), overrides self.m with FasterGhostBottleneck.
    Constructor signature matches C3k2 exactly so parse_model YAML args
    map correctly: (c1, c2, n, c3k, e, attn, g, shortcut).
    c3k and attn are accepted but ignored — always uses FasterGhostBottleneck.

    Replaces C3k2 in neck layers 13, 16, 19 only.
    Layer 22 (C3k2 with attn=True / PSABlock) must NOT be replaced.
    """

    def __init__(
        self,
        c1: int,
        c2: int,
        n: int = 1,
        c3k: bool = False,
        e: float = 0.5,
        attn: bool = False,
        g: int = 1,
        shortcut: bool = True,
    ):
        super().__init__(c1, c2, n, shortcut, g, e)
        self.m = nn.ModuleList(
            FasterGhostBottleneck(self.c, self.c, shortcut, g, e=1.0) for _ in range(n)
        )


def register_custom_modules() -> None:
    """Inject custom module classes into ultralytics.nn.tasks globals.

    Must be called BEFORE YOLO('custom.yaml') so parse_model() can
    resolve 'S2DConv', 'FasterGhostConv', and 'FasterGhostC3k2' token names.

    Also patches parse_model() to include custom modules in base_modules
    and repeat_modules frozensets so that (c1, c2) channel tracking and
    n-repeat insertion work correctly.
    """
    import ultralytics.nn.tasks as _tasks

    # 1. Expose class names in tasks module namespace (for globals() lookup in parse_model)
    _tasks.S2DConv = S2DConv  # type: ignore[attr-defined]
    _tasks.FasterGhostConv = FasterGhostConv  # type: ignore[attr-defined]
    _tasks.FasterGhostC3k2 = FasterGhostC3k2  # type: ignore[attr-defined]

    # 2. Patch parse_model to include custom modules in base_modules + repeat_modules.
    #    Both frozensets end with "A2C2f,\n        }" — str.replace hits both.
    #    Adding S2DConv/FasterGhostConv to repeat_modules is harmless (extra n=1
    #    maps to their k=1 default). FasterGhostC3k2 MUST be in repeat_modules
    #    so parse_model inserts n at position 2 (like C3k2).
    if not getattr(_tasks, "_custom_base_modules_patched", False):
        import inspect

        src = inspect.getsource(_tasks.parse_model)
        # Try Phase 1 marker first (already patched), then original
        phase1_marker = "A2C2f,\n            S2DConv,\n            FasterGhostConv,\n        }"
        original_marker = "A2C2f,\n        }"
        target = "A2C2f,\n            S2DConv,\n            FasterGhostConv,\n            FasterGhostC3k2,\n        }"

        if phase1_marker in src:
            src = src.replace(phase1_marker, target)
        elif original_marker in src:
            src = src.replace(original_marker, target)
        else:
            print("[UAV-MODULES] WARNING: could not patch base_modules/repeat_modules "
                  "(marker not found). Custom YAML may fail. Ultralytics version may have changed.")
            return

        compiled = compile(src, _tasks.parse_model.__code__.co_filename, "exec")
        exec(compiled, _tasks.__dict__)  # noqa: S102
        _tasks._custom_base_modules_patched = True  # type: ignore[attr-defined]
        print("[UAV-MODULES] parse_model patched: S2DConv + FasterGhostConv + FasterGhostC3k2 "
              "in base_modules & repeat_modules")
