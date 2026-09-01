"""Network API: config, bases, targets, chat."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import network as net
from services.security import require_role

router = APIRouter(prefix="/api/network", tags=["network"])


class ConfigBody(BaseModel):
    mode: str = Field(default="off", pattern="^(off|server|client)$")
    server_ip: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    base_name: str = "База-1"


class TargetBody(BaseModel):
    class_name: str
    confidence: float = 0.0
    gps_lat: float | None = None
    gps_lon: float | None = None
    crop_path: str | None = None
    notes: str | None = None
    source_base: str | None = None
    source_video: str | None = None


class MessageBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)


class HeartbeatBody(BaseModel):
    base_id: str
    base_name: str = "База"
    ip: str = "127.0.0.1"


@router.get("/config")
async def get_config(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, Any]:
    return net.get_config()


@router.post("/config")
async def post_config(
    body: ConfigBody,
    _user: dict[str, Any] = Depends(require_role("engineer")),
) -> dict[str, Any]:
    return net.save_config(
        mode=body.mode,
        server_ip=body.server_ip,
        port=body.port,
        base_name=body.base_name,
    )


@router.get("/bases")
async def get_bases(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, Any]:
    return {"bases": net.list_bases()}


@router.post("/heartbeat")
async def post_heartbeat(
    body: HeartbeatBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    net.heartbeat(body.base_id, body.base_name, body.ip)
    return {"ok": True}


@router.get("/targets")
async def get_targets(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, Any]:
    return {"targets": net.list_targets()}


@router.post("/targets")
async def post_target(
    body: TargetBody,
    user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    cfg = net.get_config()
    if cfg.get("mode") == "off":
        raise HTTPException(status_code=400, detail="Сеть выключена (mode=off)")
    row = net.add_target(
        direction="out",
        class_name=body.class_name,
        confidence=body.confidence,
        gps_lat=body.gps_lat,
        gps_lon=body.gps_lon,
        crop_path=body.crop_path,
        source_base=body.source_base or cfg.get("base_name") or str(user.get("role")),
        source_video=body.source_video,
        notes=body.notes,
    )
    # Mirror as incoming for local demo / multi-client same DB
    net.add_target(
        direction="in",
        class_name=body.class_name,
        confidence=body.confidence,
        gps_lat=body.gps_lat,
        gps_lon=body.gps_lon,
        crop_path=body.crop_path,
        source_base=body.source_base or cfg.get("base_name"),
        source_video=body.source_video,
        notes=body.notes,
    )
    return {"ok": True, "target": row}


@router.get("/messages")
async def get_messages(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, Any]:
    return {"messages": net.list_messages()}


@router.post("/messages")
async def post_message(
    body: MessageBody,
    user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    cfg = net.get_config()
    if cfg.get("mode") == "off":
        raise HTTPException(status_code=400, detail="Сеть выключена (mode=off)")
    sender = cfg.get("base_name") or str(user.get("role"))
    msg = net.add_message(direction="out", sender=str(sender), body=body.body)
    net.add_message(direction="in", sender=str(sender), body=body.body)
    return {"ok": True, "message": msg}
