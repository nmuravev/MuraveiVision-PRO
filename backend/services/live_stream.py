"""Per-viewer live ingest: RTSP / UDP / HTTP(MJPEG) via OpenCV → JPEG frames."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

_JPEG_QUALITY = 80
_MAX_VIEWERS = 4
_READ_TIMEOUT_SEC = 8.0
_OPEN_TIMEOUT_SEC = 8.0


@dataclass
class _LiveSession:
    viewer_id: str
    url: str
    stop: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    jpeg: bytes | None = None
    frame_idx: int = 0
    width: int = 0
    height: int = 0
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    last_frame_at: float = 0.0
    active: bool = True


class LiveStreamManager:
    def __init__(self) -> None:
        self._sessions: dict[str, _LiveSession] = {}
        self._lock = threading.Lock()

    def open(self, viewer_id: str, url: str) -> dict[str, Any]:
        viewer_id = (viewer_id or "").strip()
        url = (url or "").strip()
        if not viewer_id:
            raise ValueError("viewer_id required")
        if not url:
            raise ValueError("url required")
        low = url.lower()
        if not (
            low.startswith("rtsp://")
            or low.startswith("rtsps://")
            or low.startswith("udp://")
            or low.startswith("http://")
            or low.startswith("https://")
        ):
            raise ValueError("URL must be rtsp://, udp://, or http(s)://")
        with self._lock:
            if viewer_id in self._sessions:
                self._stop_unlocked(viewer_id)
            if len(self._sessions) >= _MAX_VIEWERS and viewer_id not in self._sessions:
                raise ValueError(f"max {_MAX_VIEWERS} live viewers")
            session = _LiveSession(viewer_id=viewer_id, url=url, active=True)
            session.thread = threading.Thread(
                target=self._capture_loop,
                args=(session,),
                name=f"live-{viewer_id}",
                daemon=True,
            )
            self._sessions[viewer_id] = session
            session.thread.start()
        return self.status(viewer_id)

    def close(self, viewer_id: str) -> dict[str, Any]:
        with self._lock:
            existed = viewer_id in self._sessions
            self._stop_unlocked(viewer_id)
        return {"ok": True, "viewer_id": viewer_id, "closed": existed}

    def _stop_unlocked(self, viewer_id: str) -> None:
        session = self._sessions.pop(viewer_id, None)
        if session is None:
            return
        with session.lock:
            session.active = False
        session.stop.set()
        thread = session.thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def status(self, viewer_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(viewer_id)
        if session is None:
            return {"viewer_id": viewer_id, "active": False}
        thread = session.thread
        alive = bool(thread is not None and thread.is_alive())
        with session.lock:
            opening_timed_out = (
                session.last_frame_at <= 0
                and time.time() - session.started_at > _OPEN_TIMEOUT_SEC
            )
            if opening_timed_out:
                session.active = False
                session.error = session.error or "stream open timeout"
                session.stop.set()
            active = bool(session.active and alive and not opening_timed_out)
            return {
                "viewer_id": viewer_id,
                "active": active,
                "url": session.url,
                "frame_idx": session.frame_idx,
                "width": session.width,
                "height": session.height,
                "error": session.error,
                "last_frame_at": session.last_frame_at,
                "age_ms": int((time.time() - session.last_frame_at) * 1000)
                if session.last_frame_at
                else None,
                "has_frame": session.jpeg is not None,
            }

    def list_status(self) -> list[dict[str, Any]]:
        with self._lock:
            ids = list(self._sessions.keys())
        return [self.status(vid) for vid in ids]

    def latest_jpeg(self, viewer_id: str) -> bytes | None:
        with self._lock:
            session = self._sessions.get(viewer_id)
        if session is None:
            return None
        with session.lock:
            return session.jpeg

    def _capture_loop(self, session: _LiveSession) -> None:
        cap = None
        try:
            try:
                import cv2
            except ImportError:
                with session.lock:
                    session.error = "opencv not installed"
                    session.active = False
                return

            # Prefer FFMPEG backend for RTSP/UDP on Windows.
            try:
                params: list[int] = []
                if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                    params.extend([int(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC), int(_OPEN_TIMEOUT_SEC * 1000)])
                if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                    params.extend([int(cv2.CAP_PROP_READ_TIMEOUT_MSEC), int(_READ_TIMEOUT_SEC * 1000)])
                cap = cv2.VideoCapture(session.url, cv2.CAP_FFMPEG, params)
                if not cap.isOpened():
                    cap.release()
                    with session.lock:
                        session.error = "cannot open stream"
                        session.active = False
                    return
                # Reduce buffering for live latency when supported.
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:  # noqa: BLE001
                    pass

                last_ok = time.time()
                while not session.stop.is_set():
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        if time.time() - last_ok > _READ_TIMEOUT_SEC:
                            with session.lock:
                                session.error = "stream read timeout"
                            break
                        time.sleep(0.05)
                        continue
                    last_ok = time.time()
                    h, w = frame.shape[:2]
                    ok_enc, buf = cv2.imencode(
                        ".jpg",
                        frame,
                        [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY],
                    )
                    if not ok_enc:
                        continue
                    jpeg = buf.tobytes()
                    with session.lock:
                        session.jpeg = jpeg
                        session.frame_idx += 1
                        session.width = int(w)
                        session.height = int(h)
                        session.last_frame_at = time.time()
                        session.error = None
                    # Pace lightly; RTSP delivers its own fps.
                    time.sleep(0.001)
            except Exception as exc:  # noqa: BLE001
                with session.lock:
                    session.error = str(exc)
        finally:
            with session.lock:
                session.active = False
            if cap is not None:
                try:
                    cap.release()
                except Exception:  # noqa: BLE001
                    pass


_manager: LiveStreamManager | None = None


def get_live_manager() -> LiveStreamManager:
    global _manager
    if _manager is None:
        _manager = LiveStreamManager()
    return _manager
