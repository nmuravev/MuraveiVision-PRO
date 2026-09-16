"""WebSocket chat: local browsers + backend peer relay on hub."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services import network as net
from services import chat_ws
from services.security import ROLE_LEVEL, decode_token

logger = logging.getLogger("muravei.ws_chat")

router = APIRouter(tags=["network"])


def _auth_ws(token: str | None) -> dict | None:
    try:
        user = decode_token(token or "")
        if ROLE_LEVEL.get(str(user.get("role", "")), 0) < ROLE_LEVEL["operator"]:
            return None
        return user
    except Exception:  # noqa: BLE001
        return None


@router.websocket("/ws/chat")
async def network_chat_ws(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    is_peer = websocket.query_params.get("peer") == "1"
    user = _auth_ws(token)
    if user is None:
        await websocket.close(code=4401)
        return

    if is_peer:
        if net.get_config().get("mode") != "server":
            await websocket.close(code=4403)
            return
        await websocket.accept()
        logger.info("WS chat peer connected role=%s", user.get("role"))
        try:
            while True:
                text = await websocket.receive_text()
                await chat_ws.handle_peer_inbound(websocket, text)
        except WebSocketDisconnect:
            logger.info("WS chat peer disconnected")
        finally:
            await chat_ws.unregister_peer(websocket)
        return

    await websocket.accept()
    await chat_ws.register_browser(websocket)
    logger.info("WS chat browser connected role=%s", user.get("role"))
    try:
        while True:
            text = await websocket.receive_text()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        logger.info("WS chat browser disconnected")
    finally:
        await chat_ws.unregister_browser(websocket)
