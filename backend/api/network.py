"""Network API: config, bases, targets, chat."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from services import chat_ws
from services import network as net
from services import network_attachments as nattach
from services.network_sync import get_worker
from services.security import require_role

router = APIRouter(prefix="/api/network", tags=["network"])


class ConfigBody(BaseModel):
    mode: str = Field(default="off", pattern="^(off|server|client)$")
    server_ip: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    base_name: str = "База-1"
    hub_pin: str | None = None


class TargetBody(BaseModel):
    id: str | None = None
    class_name: str
    confidence: float = 0.0
    gps_lat: float | None = None
    gps_lon: float | None = None
    crop_path: str | None = None
    notes: str | None = None
    source_base: str | None = None
    source_video: str | None = None


class MessageBody(BaseModel):
    id: str | None = None
    body: str = Field(..., min_length=1, max_length=2000)
    sender: str | None = None
    created_at: float | None = None
    attachment_id: str | None = None


class AttachmentInitBody(BaseModel):
    filename: str = Field(..., min_length=1, max_length=200)
    content_type: str = Field(..., min_length=3, max_length=100)
    size: int = Field(..., ge=1, le=8 * 1024 * 1024)
    sha256: str = Field(..., min_length=64, max_length=64)
    id: str | None = None


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
        hub_pin=body.hub_pin,
    )


@router.get("/bases")
async def get_bases(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, Any]:
    return {"bases": net.list_bases()}


@router.get("/status")
async def get_network_status(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    from services import network_sync as nsync

    return nsync.status_dict()


@router.post("/heartbeat")
async def post_heartbeat(
    body: HeartbeatBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    net.heartbeat(body.base_id, body.base_name, body.ip)
    return {"ok": True}


@router.get("/targets")
async def get_targets(
    since: float | None = None,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return {"targets": net.list_targets(since=since)}


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
        target_id=body.id,
    )
    return {"ok": True, "target": row}


@router.get("/messages")
async def get_messages(
    since: float | None = None,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return {"messages": net.list_messages(since=since)}


@router.post("/messages")
async def post_message(
    body: MessageBody,
    user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    cfg = net.get_config()
    if cfg.get("mode") == "off":
        raise HTTPException(status_code=400, detail="Сеть выключена (mode=off)")
    sender = (body.sender or "").strip() or cfg.get("base_name") or str(user.get("role"))
    if body.attachment_id and not nattach.is_complete(str(body.attachment_id)):
        raise HTTPException(status_code=400, detail="attachment not ready")
    msg = net.add_message(
        direction="out",
        sender=str(sender),
        body=body.body,
        message_id=body.id,
        created_at=body.created_at,
        attachment_id=body.attachment_id,
    )
    relay_peers = cfg.get("mode") == "server"
    await chat_ws.emit_chat_message(msg, relay_peers=relay_peers)
    worker = get_worker()
    if worker is not None and cfg.get("mode") == "client":
        asyncio.create_task(worker.push_local_messages())
        asyncio.create_task(worker.relay_message_to_hub(msg))
    return {"ok": True, "message": msg}


@router.post("/attachments")
async def post_attachment_init(
    body: AttachmentInitBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    cfg = net.get_config()
    if cfg.get("mode") == "off":
        raise HTTPException(status_code=400, detail="Сеть выключена (mode=off)")
    try:
        meta = nattach.init_attachment(
            filename=body.filename,
            content_type=body.content_type,
            size=body.size,
            sha256=body.sha256,
            attachment_id=body.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "attachment": meta}


@router.put("/attachments/{attachment_id}/chunks/{index}")
async def put_attachment_chunk(
    attachment_id: str,
    index: int,
    request: Request,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    data = await request.body()
    try:
        meta = nattach.put_chunk(attachment_id, index, data)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "id": meta.get("id"), "index": index}


@router.post("/attachments/{attachment_id}/finalize")
async def post_attachment_finalize(
    attachment_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        meta = nattach.finalize_attachment(attachment_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "attachment": meta}


@router.get("/attachments/{attachment_id}")
async def get_attachment_meta(
    attachment_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    meta = nattach.read_meta(attachment_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="attachment not found")
    return {"attachment": meta}


@router.get("/attachments/{attachment_id}/chunks/{index}")
async def get_attachment_chunk(
    attachment_id: str,
    index: int,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> Response:
    try:
        raw = nattach.read_chunk_bytes(attachment_id, index)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=raw, media_type="application/octet-stream")


@router.get("/attachments/{attachment_id}/bytes")
async def get_attachment_bytes(
    attachment_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> Response:
    try:
        raw, meta = nattach.read_blob(attachment_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ctype = str(meta.get("content_type") or "application/octet-stream")
    filename = str(meta.get("filename") or "attach.bin")
    return Response(
        content=raw,
        media_type=ctype,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/messages/unread")
async def get_unread(
    since: float = 0.0,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return {"count": net.count_incoming_messages_since(since)}

