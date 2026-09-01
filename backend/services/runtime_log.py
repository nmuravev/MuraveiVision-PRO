"""In-memory runtime log for DebugPanel (commands, subprocess, backend events)."""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
LOG_PATH = BASE_DIR / "logs" / "runtime.log"

MAX_ENTRIES = 2000
_lock = threading.Lock()
_entries: list[dict[str, Any]] = []
_seq = 0


def _mirror_file(line: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def write(
    level: str,
    source: str,
    message: str,
    *,
    kind: str = "text",
) -> dict[str, Any]:
    global _seq
    level = level if level in ("error", "warn", "info", "debug", "verbose") else "info"
    with _lock:
        _seq += 1
        entry: dict[str, Any] = {
            "id": f"rt-{_seq}",
            "ts": time.time(),
            "level": level,
            "source": source,
            "message": message,
            "kind": kind,
        }
        _entries.append(entry)
        if len(_entries) > MAX_ENTRIES:
            del _entries[: MAX_ENTRIES // 2]
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    _mirror_file(f"{stamp} [{level}] [{source}] {message}")
    print(f"[{source}] {message}")
    return entry


def info(source: str, message: str) -> dict[str, Any]:
    return write("info", source, message)


def warn(source: str, message: str) -> dict[str, Any]:
    return write("warn", source, message)


def error(source: str, message: str) -> dict[str, Any]:
    return write("error", source, message)


def debug(source: str, message: str) -> dict[str, Any]:
    return write("debug", source, message)


def verbose(source: str, message: str) -> dict[str, Any]:
    return write("verbose", source, message)


def cmd(source: str, argv: list[str] | str) -> dict[str, Any]:
    line = argv if isinstance(argv, str) else " ".join(str(x) for x in argv)
    if not line.startswith("$"):
        line = f"$ {line}"
    return write("info", source, line, kind="cmd")


def count() -> int:
    with _lock:
        return len(_entries)


def recent(limit: int = 400) -> list[dict[str, Any]]:
    with _lock:
        return list(_entries[-limit:])


def drain(after_idx: int = 0) -> tuple[list[dict[str, Any]], int]:
    with _lock:
        chunk = list(_entries[after_idx:])
        return chunk, len(_entries)


def clear() -> None:
    with _lock:
        _entries.clear()


def logged_run(
    cmd_argv: list[str],
    source: str,
    *,
    timeout: float | int = 3600,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    cmd(source, cmd_argv)
    try:
        proc = subprocess.run(
            cmd_argv,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        warn(source, f"timeout after {timeout}s")
        raise exc
    except OSError as exc:
        error(source, f"spawn failed: {exc}")
        raise

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        if err:
            for line in err.splitlines()[:8]:
                write("warn", source, line, kind="stderr")
        warn(source, f"exit code {proc.returncode}")
    else:
        debug(source, "exit 0")
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd_argv, proc.stdout, proc.stderr)
    return proc
