"""Training + dataset export for operator."""
from __future__ import annotations

import asyncio
import io
import json
import zipfile
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.db import CROPS_DIR, list_detections
from services.security import require_role
from services import trainer

router = APIRouter(tags=["train"])


def _build_dataset_yaml(names: list[str]) -> str:
    lines = ["path: .", "train: images", "val: images", "names:"]
    if not names:
        lines.append("  0: unlabeled")
    else:
        for idx, name in enumerate(names):
            lines.append(f"  {idx}: {name}")
    return "\n".join(lines) + "\n"


def _yolo_line(class_idx: int, row: dict[str, Any]) -> str:
    cx = float(row["bbox_x"]) + float(row["bbox_w"]) / 2.0
    cy = float(row["bbox_y"]) + float(row["bbox_h"]) / 2.0
    return (
        f"{class_idx} {max(0.0, min(1.0, cx)):.6f} {max(0.0, min(1.0, cy)):.6f} "
        f"{max(0.0, min(1.0, float(row['bbox_w']))):.6f} {max(0.0, min(1.0, float(row['bbox_h']))):.6f}\n"
    )


@router.post("/api/export/dataset-zip")
async def export_dataset_zip(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> StreamingResponse:
    detections = list_detections(include_deleted=False)
    names: list[str] = list(
        OrderedDict((str(d["class_name"]), None) for d in detections).keys()
    )
    name_to_idx = {name: i for i, name in enumerate(names)}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("dataset.yaml", _build_dataset_yaml(names))
        zf.writestr(
            "detections.json",
            json.dumps(detections, ensure_ascii=False, indent=2),
        )
        zf.writestr(
            "README_ENGINEER.txt",
            "\n".join(
                [
                    "MuraveiVision PRO — датасет для инженера",
                    f"Создан: {datetime.now(timezone.utc).isoformat()}",
                    "images/ — кропы из archive/crops/",
                    "labels/ — YOLO txt (cx cy w h, нормализованные)",
                    "dataset.yaml — имена классов",
                    "PIN-коды в архив не входят.",
                    "",
                ]
            ),
        )
        if CROPS_DIR.is_dir():
            for crop in sorted(CROPS_DIR.glob("*.jpg")):
                zf.write(crop, f"images/{crop.name}")
                zf.write(crop, f"archive/crops/{crop.name}")
        for row in detections:
            crop_name = f"{row['id']}.jpg"
            label_name = f"{row['id']}.txt"
            idx = name_to_idx.get(str(row["class_name"]), 0)
            zf.writestr(f"labels/{label_name}", _yolo_line(idx, row))
            src = Path(str(row["crop_path"])) if row.get("crop_path") else CROPS_DIR / crop_name
            if src.is_file() and f"images/{crop_name}" not in zf.namelist():
                zf.write(src, f"images/{crop_name}")

    buf.seek(0)
    filename = f"muravei-dataset-{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    print(f"[EXPORT] dataset zip detections={len(detections)} names={len(names)}")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class TrainStartBody(BaseModel):
    epochs: int = Field(default=10, ge=1, le=50)
    resume_from: str | None = None
    imgsz: int = Field(default=640, ge=320, le=1024)
    batch: int = Field(default=4, ge=1, le=8)


@router.get("/api/train/status")
async def train_status(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, Any]:
    return trainer.status()


@router.get("/api/train/checkpoints")
async def train_checkpoints(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return trainer.list_checkpoints()


@router.post("/api/train/start")
async def train_start(
    body: TrainStartBody | None = None,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    epochs = body.epochs if body else 10
    resume_from = body.resume_from if body else None
    imgsz = body.imgsz if body else 640
    batch = body.batch if body else 4
    try:
        return trainer.start(
            epochs=epochs,
            resume_from=resume_from,
            imgsz=imgsz,
            batch=batch,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/train/stop")
async def train_stop(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, Any]:
    return trainer.stop()


@router.get("/api/train/stream")
async def train_stream(_user: dict[str, Any] = Depends(require_role("operator"))) -> StreamingResponse:
    async def gen():
        idx = 0
        # send current status immediately
        yield f"data: {json.dumps({'type': 'status', **trainer.status()}, ensure_ascii=False)}\n\n"
        while True:
            events, idx = trainer.drain_events(idx)
            for ev in events:
                yield f"data: {json.dumps({'type': 'progress', **ev}, ensure_ascii=False)}\n\n"
                if ev.get("status") in ("done", "error", "idle"):
                    return
            st = trainer.status()
            if st.get("status") in ("done", "error", "idle") and not events:
                yield f"data: {json.dumps({'type': 'status', **st}, ensure_ascii=False)}\n\n"
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")
