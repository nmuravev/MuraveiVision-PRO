"""Client-side hub sync worker: heartbeat, push unsynced out, pull incremental in."""
from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any

import httpx
import jwt
import websockets

from services import chat_ws
from services import network as net

SYNC_INTERVAL_SEC = 15.0
HTTP_TIMEOUT_SEC = 10.0
TOKEN_REFRESH_SKEW_SEC = 60.0


def _exp_from_token(token: str) -> float:
    try:
        payload = jwt.decode(
            token,
            algorithms=["HS256"],
            options={"verify_signature": False, "verify_exp": False},
        )
        exp = payload.get("exp")
        if exp is not None:
            return float(exp)
    except Exception:  # noqa: BLE001
        pass
    return time.time() + 8 * 3600


class NetworkSyncWorker:
    def __init__(self) -> None:
        self.base_id: str = ""
        self.base_name: str = ""
        self.server_ip: str = ""
        self.port: int = 8000
        self.hub_token: str | None = None
        self.hub_token_expires: float | None = None
        self.cursor: float | None = None
        self.message_cursor: float | None = None
        self.last_error: str | None = None
        self.last_sync_ts: float | None = None
        self.hub_reachable: bool = False
        self.advertise_ip: str = ""
        self.running: bool = False
        self.lock: asyncio.Lock = asyncio.Lock()
        self.task: asyncio.Task[None] | None = None
        self.ws_peer: str = "down"
        self.ws_peer_last_error: str | None = None
        self._peer_ws: Any = None
        self._peer_backoff: float = 1.0

    def _hub_base(self) -> str:
        ip = (self.server_ip or "127.0.0.1").strip()
        return f"http://{ip}:{int(self.port)}"

    def _hub_url(self, path: str) -> str:
        return f"{self._hub_base()}{path}"

    def _token_fresh(self) -> bool:
        if not self.hub_token or self.hub_token_expires is None:
            return False
        return time.time() < (self.hub_token_expires - TOKEN_REFRESH_SKEW_SEC)

    def _is_self_source(self, source_base: str | None) -> bool:
        src = (source_base or "").strip()
        if not src:
            return False
        names = {n for n in (self.base_id, self.base_name) if n}
        return src in names

    def _reload_identity(self) -> dict[str, Any]:
        cfg = net.get_config()
        self.base_id = net.ensure_base_id()
        self.base_name = str(cfg.get("base_name") or "")
        self.server_ip = str(cfg.get("server_ip") or "").strip()
        self.port = int(cfg.get("port") or 8000)
        return cfg

    async def login_to_hub(self, force: bool = False) -> bool:
        async with self.lock:
            if not force and self._token_fresh():
                return True
            pin = net.get_hub_pin()
            if not pin:
                self.hub_reachable = False
                self.last_error = "hub PIN not set"
                print("[NETWORK] Hub login failed: no PIN")
                return False
            try:
                async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC) as client:
                    resp = await client.post(
                        self._hub_url("/api/auth/login"),
                        json={"pin": pin},
                    )
            except Exception as exc:  # noqa: BLE001
                self.hub_reachable = False
                self.hub_token = None
                self.last_error = str(exc)
                print(f"[NETWORK] Hub login failed: {exc}")
                print("[NETWORK] offline")
                return False
            if resp.status_code != 200:
                self.hub_reachable = False
                self.hub_token = None
                self.last_error = f"Hub login HTTP {resp.status_code}"
                print("[NETWORK] Hub login failed")
                return False
            token = str((resp.json() or {}).get("token") or "")
            if not token:
                self.hub_reachable = False
                self.last_error = "Hub login: empty token"
                print("[NETWORK] Hub login failed")
                return False
            self.hub_token = token
            self.hub_token_expires = _exp_from_token(token)
            self.hub_reachable = True
            return True

    async def _authed_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retried: bool = False,
    ) -> httpx.Response | None:
        if not await self.login_to_hub():
            return None
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC) as client:
                resp = await client.request(
                    method,
                    self._hub_url(path),
                    headers={
                        "Authorization": f"Bearer {self.hub_token}",
                        "Content-Type": "application/json",
                    },
                    json=json,
                    params=params,
                )
        except Exception as exc:  # noqa: BLE001
            self.hub_reachable = False
            self.last_error = str(exc)
            print(f"[NETWORK] offline: {exc}")
            return None
        if resp.status_code == 401 and not retried:
            if await self.login_to_hub(force=True):
                return await self._authed_request(
                    method, path, json=json, params=params, retried=True
                )
            return resp
        if resp.status_code < 500:
            self.hub_reachable = True
        return resp

    async def send_heartbeat(self) -> bool:
        self.advertise_ip = net.resolve_lan_ipv4()
        resp = await self._authed_request(
            "POST",
            "/api/network/heartbeat",
            json={
                "base_id": self.base_id,
                "base_name": self.base_name or "База",
                "ip": self.advertise_ip,
            },
        )
        if resp is None:
            self.hub_reachable = False
            return False
        if resp.status_code >= 400:
            self.hub_reachable = False
            self.last_error = f"heartbeat HTTP {resp.status_code}"
            print(f"[NETWORK] heartbeat failed: HTTP {resp.status_code}")
            return False
        self.hub_reachable = True
        return True

    async def push_local_targets(self) -> int:
        rows = net.list_unsynced_out_targets()
        pushed = 0
        for row in rows:
            tid = str(row.get("id") or "")
            if not tid:
                continue
            resp = await self._authed_request(
                "POST",
                "/api/network/targets",
                json={
                    "id": tid,
                    "class_name": row.get("class_name"),
                    "confidence": row.get("confidence") or 0,
                    "gps_lat": row.get("gps_lat"),
                    "gps_lon": row.get("gps_lon"),
                    "crop_path": row.get("crop_path"),
                    "source_base": row.get("source_base") or self.base_name,
                    "source_video": row.get("source_video"),
                    "notes": row.get("notes"),
                },
            )
            if resp is None or resp.status_code >= 400:
                code = resp.status_code if resp is not None else "offline"
                print(f"[NETWORK] push failed id={tid}: {code}")
                continue
            net.mark_target_synced(tid)
            pushed += 1
        return pushed

    async def pull_remote_targets(self) -> int:
        since = float(self.cursor) if self.cursor is not None else 0.0
        resp = await self._authed_request(
            "GET",
            "/api/network/targets",
            params={"since": since},
        )
        if resp is None or resp.status_code >= 400:
            if resp is not None:
                self.last_error = f"pull HTTP {resp.status_code}"
                print(f"[NETWORK] pull failed: HTTP {resp.status_code}")
            return 0
        items = (resp.json() or {}).get("targets") or []
        if not isinstance(items, list):
            return 0
        upserted = 0
        newest = self.cursor
        for item in items:
            if not isinstance(item, dict):
                continue
            created = item.get("created_at")
            if created is not None:
                created_f = float(created)
                newest = created_f if newest is None else max(newest, created_f)
            if self._is_self_source(item.get("source_base")):
                continue
            tid = str(item.get("id") or "").strip()
            class_name = str(item.get("class_name") or "").strip()
            if not tid or not class_name:
                continue
            net.upsert_target(
                target_id=tid,
                class_name=class_name,
                confidence=float(item.get("confidence") or 0),
                gps_lat=item.get("gps_lat"),
                gps_lon=item.get("gps_lon"),
                crop_path=item.get("crop_path"),
                source_base=item.get("source_base"),
                source_video=item.get("source_video"),
                notes=item.get("notes"),
                created_at=float(created) if created is not None else None,
                expires_at=item.get("expires_at"),
            )
            upserted += 1
        if newest is not None:
            self.cursor = newest
        return upserted

    async def push_local_messages(self) -> int:
        rows = net.list_unsynced_out_messages()
        pushed = 0
        for row in rows:
            mid = str(row.get("id") or "")
            if not mid:
                continue
            resp = await self._authed_request(
                "POST",
                "/api/network/messages",
                json={
                    "id": mid,
                    "body": row.get("body") or "",
                    "sender": row.get("sender") or self.base_name,
                    "created_at": row.get("created_at"),
                },
            )
            if resp is None or resp.status_code >= 400:
                code = resp.status_code if resp is not None else "offline"
                print(f"[NETWORK] message push failed id={mid}: {code}")
                continue
            net.mark_message_synced(mid)
            pushed += 1
        return pushed

    async def pull_remote_messages(self) -> int:
        since = float(self.message_cursor) if self.message_cursor is not None else 0.0
        resp = await self._authed_request(
            "GET",
            "/api/network/messages",
            params={"since": since},
        )
        if resp is None or resp.status_code >= 400:
            if resp is not None:
                self.last_error = f"message pull HTTP {resp.status_code}"
                print(f"[NETWORK] message pull failed: HTTP {resp.status_code}")
            return 0
        items = (resp.json() or {}).get("messages") or []
        if not isinstance(items, list):
            return 0
        upserted = 0
        newest = self.message_cursor
        for item in items:
            if not isinstance(item, dict):
                continue
            created = item.get("created_at")
            if created is not None:
                created_f = float(created)
                newest = created_f if newest is None else max(newest, created_f)
            sender = str(item.get("sender") or "").strip()
            if self._is_self_source(sender):
                continue
            mid = str(item.get("id") or "").strip()
            body = str(item.get("body") or "")
            if not mid or not body.strip():
                continue
            # Already have this row locally (e.g. our own out mirrored on hub) — skip dup
            existing = net.get_message(mid)
            if existing is not None and str(existing.get("direction")) == "out":
                continue
            net.upsert_message(
                message_id=mid,
                sender=sender or "База",
                body=body,
                created_at=float(created) if created is not None else None,
                expires_at=item.get("expires_at"),
            )
            upserted += 1
            row = net.get_message(mid)
            if row is not None:
                await chat_ws.emit_chat_message(row)
        if newest is not None:
            self.message_cursor = newest
        return upserted

    async def relay_message_to_hub(self, row: dict[str, Any]) -> None:
        ws = self._peer_ws
        if ws is None or self.ws_peer != "connected":
            return
        payload = json.dumps(
            {"type": "chat.message", "message": chat_ws.public_message(row)},
        )
        try:
            await ws.send(payload)
        except Exception as exc:  # noqa: BLE001
            self.ws_peer = "down"
            self.ws_peer_last_error = str(exc)

    async def _handle_hub_chat_frame(self, text: str) -> None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict) or data.get("type") != "chat.message":
            return
        raw = data.get("message")
        if not isinstance(raw, dict):
            return
        sender = str(raw.get("sender") or "").strip()
        if self._is_self_source(sender):
            return
        mid = str(raw.get("id") or "").strip()
        body = str(raw.get("body") or "").strip()
        if not mid or not body:
            return
        created = raw.get("created_at")
        net.upsert_message(
            message_id=mid,
            sender=sender or "База",
            body=body,
            created_at=float(created) if created is not None else None,
        )
        got = net.get_message(mid)
        if got is not None:
            await chat_ws.emit_chat_message(got)

    async def _peer_backoff_sleep(self) -> None:
        delay = min(60.0, self._peer_backoff) + random.uniform(0, 0.5)
        await asyncio.sleep(delay)
        self._peer_backoff = min(60.0, self._peer_backoff * 2)

    async def run_chat_peer(self) -> None:
        self._peer_backoff = 1.0
        print("[NETWORK] chat peer loop started")
        try:
            while self.running:
                cfg = self._reload_identity()
                if cfg.get("mode") != "client":
                    self.ws_peer = "down"
                    self.ws_peer_last_error = None
                    self._peer_ws = None
                    await asyncio.sleep(2.0)
                    continue
                if not await self.login_to_hub():
                    self.ws_peer = "down"
                    self.ws_peer_last_error = self.last_error
                    await self._peer_backoff_sleep()
                    continue
                ip = (self.server_ip or "127.0.0.1").strip()
                port = int(self.port)
                token = self.hub_token or ""
                url = f"ws://{ip}:{port}/ws/chat?token={token}&peer=1"
                try:
                    async with websockets.connect(
                        url,
                        open_timeout=HTTP_TIMEOUT_SEC,
                        close_timeout=5,
                    ) as ws:
                        self._peer_ws = ws
                        self.ws_peer = "connected"
                        self.ws_peer_last_error = None
                        self._peer_backoff = 1.0
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "peer.hello",
                                    "base_id": self.base_id,
                                    "base_name": self.base_name,
                                }
                            )
                        )
                        async for raw in ws:
                            await self._handle_hub_chat_frame(str(raw))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    self.ws_peer = "down"
                    self.ws_peer_last_error = str(exc)
                    print(f"[NETWORK] chat peer WS down: {exc}")
                    await self._peer_backoff_sleep()
                finally:
                    self._peer_ws = None
        except asyncio.CancelledError:
            print("[NETWORK] chat peer loop cancelled")
            raise
        finally:
            self._peer_ws = None
            self.ws_peer = "down"

    async def sync_tick(self) -> None:
        try:
            cfg = self._reload_identity()
            if cfg.get("mode") != "client" or not self.server_ip:
                return
            if not await self.login_to_hub():
                return
            await self.send_heartbeat()
            await self.push_local_targets()
            await self.pull_remote_targets()
            await self.push_local_messages()
            await self.pull_remote_messages()
            self.last_sync_ts = time.time()
            if self.hub_reachable:
                self.last_error = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            print(f"[NETWORK] Sync tick failed: {exc}")

    async def run(self) -> None:
        self.running = True
        print("[NETWORK] worker started")
        try:
            while self.running:
                try:
                    await self.sync_tick()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    self.last_error = str(exc)
                    print(f"[NETWORK] tick failed: {exc}")
                await asyncio.sleep(SYNC_INTERVAL_SEC)
        except asyncio.CancelledError:
            print("[NETWORK] worker cancelled")
            raise
        finally:
            self.running = False

    def stop(self) -> None:
        self.running = False


_worker: NetworkSyncWorker | None = None
_task: asyncio.Task[None] | None = None
_peer_task: asyncio.Task[None] | None = None


def get_worker() -> NetworkSyncWorker | None:
    return _worker


def worker_alive() -> bool:
    return _task is not None and not _task.done()


def status_dict() -> dict[str, Any]:
    cfg = net.get_config()
    worker = _worker
    return {
        "mode": cfg.get("mode"),
        "base_id": cfg.get("base_id") or (worker.base_id if worker else ""),
        "last_sync_ts": worker.last_sync_ts if worker else None,
        "last_error": worker.last_error if worker else None,
        "hub_reachable": bool(worker.hub_reachable) if worker else False,
        "worker_alive": worker_alive(),
        "advertise_ip": (worker.advertise_ip if worker else "") or net.resolve_lan_ipv4(),
        "sync_interval_sec": SYNC_INTERVAL_SEC,
        "ws_peer": (
            worker.ws_peer
            if worker is not None and cfg.get("mode") == "client"
            else "down"
        ),
        "ws_peer_last_error": (
            worker.ws_peer_last_error
            if worker is not None and cfg.get("mode") == "client"
            else None
        ),
    }


def start_network_worker() -> NetworkSyncWorker:
    global _worker, _task, _peer_task
    _worker = NetworkSyncWorker()
    _worker.running = True
    _task = asyncio.create_task(_worker.run(), name="network-sync")
    _worker.task = _task
    _peer_task = asyncio.create_task(_worker.run_chat_peer(), name="network-chat-peer")
    return _worker


async def stop_network_worker() -> None:
    global _worker, _task, _peer_task
    if _worker is not None:
        _worker.stop()
    if _peer_task is not None:
        _peer_task.cancel()
        try:
            await _peer_task
        except asyncio.CancelledError:
            pass
        _peer_task = None
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
