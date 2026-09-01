"""Operator review queue for active-learning feedback."""
from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.classes import class_id_for_name, is_catalog_label
from services.db import (
    decide_active_learning_sample,
    enqueue_active_learning,
    get_detection,
    list_active_learning_samples,
    list_detections,
    soft_delete_detection,
    update_detection,
)
from services.security import require_role

router = APIRouter(prefix="/api/active-learning", tags=["active-learning"])


class CollectRequest(BaseModel):
    source_video: str | None = None
    max_confidence: float = Field(default=0.5, ge=0.01, le=1.0)


class DecisionRequest(BaseModel):
    status: Literal["accepted", "rejected"]
    class_name: str | None = None


@router.get("")
async def active_learning_list(
    status: str = "pending",
    source_video: str | None = None,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    if status not in {"pending", "accepted", "rejected"}:
        raise HTTPException(status_code=400, detail="invalid status")
    rows = list_active_learning_samples(status=status, source_video=source_video)
    return {"samples": rows, "count": len(rows)}


@router.post("/collect")
async def active_learning_collect(
    body: CollectRequest,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    rows = list_detections(body.source_video, include_deleted=False)
    created = 0
    for row in rows:
        if float(row.get("confidence") or 0) > body.max_confidence:
            continue
        if enqueue_active_learning(
            str(row["id"]),
            "low_confidence",
            str(row.get("class_name") or ""),
        ):
            created += 1
    samples = list_active_learning_samples("pending", body.source_video)
    return {"ok": True, "collected": created, "samples": samples}


@router.post("/{sample_id}/decision")
async def active_learning_decision(
    sample_id: str,
    body: DecisionRequest,
    user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    pending = next(
        (row for row in list_active_learning_samples("pending") if row["id"] == sample_id),
        None,
    )
    if not pending:
        raise HTTPException(status_code=404, detail="sample not found")
    detection = get_detection(str(pending["detection_id"]))
    if not detection:
        raise HTTPException(status_code=404, detail="detection not found")

    class_name = (body.class_name or pending.get("proposed_class") or "").strip()
    if body.status == "accepted":
        if not class_name or not is_catalog_label(class_name):
            raise HTTPException(status_code=400, detail="unknown class_name")
        update_detection(
            str(detection["id"]),
            {
                "class_id": class_id_for_name(class_name),
                "class_name": class_name,
                "is_edited": 1,
                "edited_by": user.get("role"),
                "edited_at": time.time(),
            },
        )
    else:
        soft_delete_detection(str(detection["id"]), user.get("role"))

    sample = decide_active_learning_sample(
        sample_id,
        body.status,
        proposed_class=class_name or None,
    )
    return {"ok": True, "sample": sample}
