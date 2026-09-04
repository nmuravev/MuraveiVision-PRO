# KEEP: session trace — do not remove without explicit user order
"""ASGI middleware: correlate HTTP/WS with X-Muravei-Trace-Id → runtime_log + logs/trace.log."""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from starlette.types import ASGIApp, Receive, Scope, Send

from services import runtime_log

BASE_DIR = Path(__file__).resolve().parents[2]
TRACE_LOG = BASE_DIR / "logs" / "trace.log"
TRACE_HEADER = b"x-muravei-trace-id"

_enabled = os.environ.get("MURAVEI_SESSION_TRACE", "1").strip() != "0"


def is_trace_enabled() -> bool:
    return _enabled


def set_trace_enabled(on: bool) -> None:
    global _enabled
    _enabled = bool(on)
    runtime_log.info("trace", f"BE trace {'ON' if _enabled else 'PAUSED'} (code kept)")


def _append_trace_file(line: str) -> None:
    try:
        TRACE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with TRACE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def read_trace_tail(n: int = 50) -> list[str]:
    n = max(1, min(int(n), 500))
    if not TRACE_LOG.is_file():
        return []
    try:
        text = TRACE_LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-n:]


def extract_trace_id(headers: list[tuple[bytes, bytes]]) -> str:
    for k, v in headers:
        if k.lower() == TRACE_HEADER:
            raw = v.decode("latin-1", errors="replace").strip()
            if raw:
                return raw[:120]
    return f"be-{uuid.uuid4().hex[:12]}"


def write_trace_line(
    trace_id: str,
    message: str,
    *,
    level: str = "debug",
    source: str = "trace",
) -> None:
    if not _enabled:
        return
    line = f"[{trace_id}] {message}"
    _append_trace_file(line)
    runtime_log.write(level, source, line)


class SessionTraceMiddleware:
    """KEEP: session trace — do not remove without explicit user order."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        typ = scope.get("type")
        if typ not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        # Avoid feedback loop on SSE debug stream
        if path.startswith("/api/debug/stream") or path.startswith("/api/debug/recent"):
            await self.app(scope, receive, send)
            return

        if not (path.startswith("/api/") or path.startswith("/ws/")):
            await self.app(scope, receive, send)
            return

        if not _enabled:
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers") or [])
        trace_id = extract_trace_id(headers)
        # Stash for downstream (optional)
        scope["muravei_trace_id"] = trace_id

        client = ""
        if scope.get("client"):
            client = str(scope["client"][0])

        t0 = time.perf_counter()
        status_code = 0

        if typ == "websocket":
            write_trace_line(trace_id, f"WS {path} connect client={client}", source="ws")

            async def send_ws(message: dict[str, Any]) -> None:
                if message.get("type") == "websocket.close":
                    code = message.get("code", "")
                    write_trace_line(
                        trace_id,
                        f"WS {path} close code={code}",
                        source="ws",
                    )
                await send(message)

            try:
                await self.app(scope, receive, send_ws)
            except Exception as exc:  # noqa: BLE001
                write_trace_line(
                    trace_id,
                    f"WS {path} error {type(exc).__name__}: {str(exc)[:200]}",
                    level="error",
                    source="ws",
                )
                raise
            return

        method = (scope.get("method") or "GET").upper()

        async def send_http(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status") or 0)
            await send(message)

        try:
            await self.app(scope, receive, send_http)
        except Exception as exc:  # noqa: BLE001
            ms = int((time.perf_counter() - t0) * 1000)
            write_trace_line(
                trace_id,
                f"{method} {path} EXC {type(exc).__name__} {ms}ms {str(exc)[:200]}",
                level="error",
                source="http",
            )
            raise

        ms = int((time.perf_counter() - t0) * 1000)
        level = "warn" if status_code >= 400 else "debug"
        write_trace_line(
            trace_id,
            f"{method} {path} {status_code} {ms}ms client={client}",
            level=level,
            source="http",
        )


def pipeline_trace(source: str, message: str, *, level: str = "info", trace_id: str | None = None) -> None:
    """Helper for scanners / CD / geo."""
    tid = trace_id or f"pipe-{uuid.uuid4().hex[:10]}"
    write_trace_line(tid, message, level=level, source=source)
