"""Desktop launcher — UI on http://127.0.0.1:8000 (FastAPI + dist/)."""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent


def _start_backend() -> None:
    import uvicorn

    os.chdir(BACKEND)
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )


def _wait_health(timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    url = "http://127.0.0.1:8000/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.4)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="MuraveiVision PRO Desktop")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
        help="UI URL (production static via FastAPI)",
    )
    parser.add_argument(
        "--no-backend",
        action="store_true",
        help="Do not spawn FastAPI in a background thread",
    )
    parser.add_argument(
        "--health-timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for /api/health",
    )
    args = parser.parse_args()

    if not args.no_backend:
        t = threading.Thread(target=_start_backend, daemon=True)
        t.start()
        if not _wait_health(args.health_timeout):
            print("ОШИБКА: бэкенд не ответил на http://127.0.0.1:8000/api/health")
            print(f"Таймаут {args.health_timeout:.0f} с. Проверьте порт 8000 и логи.")
            return 1
        print("Бэкенд OK:", args.url)

    try:
        import webview
    except ImportError:
        print("Нужен pywebview: muravei_env\\Scripts\\pip.exe install pywebview")
        print(f"Откройте вручную: {args.url}")
        return 1

    webview.create_window(
        "MuraveiVision PRO v3.0",
        args.url,
        width=1920,
        height=1080,
        min_size=(1280, 720),
    )
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
