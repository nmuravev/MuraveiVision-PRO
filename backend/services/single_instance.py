"""Single-instance guard: prevent multiple backend copies.

Uses atomic lock-file in system TEMP directory (never in repo root).
Writes PID file for bat wait_loop to monitor process liveness.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

try:
    import msvcrt
    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False


class SingleInstanceGuard:
    """Prevent multiple backend instances via lock-file in tempfile."""

    def __init__(self):
        self.lockfile_path = Path(tempfile.gettempdir()) / ".muravei_backend.lock"
        self.pidfile_path = Path(tempfile.gettempdir()) / ".muravei_backend.pid"
        self._lockfile = None
        self._pid = None

    def acquire(self) -> bool:
        """Acquire lock. Returns True if successful, False if another instance exists."""
        # Check stale lock
        if self.lockfile_path.exists():
            try:
                old_pid = int(self.lockfile_path.read_text().strip())
                import psutil
                if not psutil.pid_exists(old_pid):
                    # Старый процесс мёртв — удаляем lock
                    try:
                        self.lockfile_path.unlink(missing_ok=True)
                    except OSError:
                        pass  # файл заблокирован msvcrt — пробуем открыть
                else:
                    return False  # другой процесс жив
            except (ValueError, PermissionError):
                # Файл заблокирован msvcrt — значит lock активен
                return False
            except Exception:
                try:
                    self.lockfile_path.unlink(missing_ok=True)
                except OSError:
                    pass

        try:
            self._lockfile = self.lockfile_path.open("w")
            self._pid = os.getpid()
            self._lockfile.write(str(self._pid))
            self._lockfile.flush()
            if _HAS_MSVCRT:
                msvcrt.locking(self._lockfile.fileno(), msvcrt.LK_NBLCK, 1)
            # Write PID file (НЕ удаляется при release — bat использует для taskkill)
            self.pidfile_path.write_text(str(self._pid))
            return True
        except (IOError, OSError):
            if self._lockfile:
                self._lockfile.close()
                self._lockfile = None
            return False

    def release(self) -> None:
        """Release lock. PID file is NOT deleted (bat wait_loop uses it)."""
        if self._lockfile:
            try:
                if _HAS_MSVCRT:
                    msvcrt.locking(self._lockfile.fileno(), msvcrt.LK_UNLCK, 1)
                self._lockfile.close()
            except Exception:
                pass
            self._lockfile = None
        # Удаляем lockfile только если он больше не заблокирован
        try:
            self.lockfile_path.unlink(missing_ok=True)
        except OSError:
            pass  # файл всё ещё заблокирован — игнорируем
        # F3: НЕ удаляем pidfile — bat использует его для taskkill


_guard: SingleInstanceGuard | None = None


def get_guard() -> SingleInstanceGuard:
    """Get or create the singleton guard instance."""
    global _guard
    if _guard is None:
        _guard = SingleInstanceGuard()
    return _guard
