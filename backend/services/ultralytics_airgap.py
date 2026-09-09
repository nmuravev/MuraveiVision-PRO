"""Air-gap guard: neutralize Ultralytics AutoUpdate / check_requirements.

Official env gates (confirmed in cached ultralytics 8.4.143 source):
  ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS → early return in check_requirements
  YOLO_AUTOINSTALL → AUTOINSTALL → gates attempt_install (uv/pip)

This module is the belt-and-suspenders backstop regardless of env-flag rename.
"""
from __future__ import annotations

import logging
import os
from typing import Any

_LOG = logging.getLogger("muravei.ultralytics_airgap")
_APPLIED = False
_WARNED = False

# Confirmed against installed ultralytics source (utils/__init__.py + utils/checks.py).
ENV_SKIP_CHECKS = "ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS"
ENV_AUTOINSTALL = "YOLO_AUTOINSTALL"

_RU_DISABLED = (
    "runtime AutoUpdate отключён: все зависимости уже в паке"
)


def apply_airgap_env() -> None:
    """Force official Ultralytics offline/install gates (idempotent)."""
    os.environ[ENV_SKIP_CHECKS] = "1"
    os.environ[ENV_AUTOINSTALL] = "0"


def _noop_check_requirements(*_args: Any, **_kwargs: Any) -> bool:
    global _WARNED
    if not _WARNED:
        _WARNED = True
        msg = _RU_DISABLED
        _LOG.info(msg)
        print(f"[AIRGAP] {msg}")
    return True


def install_check_requirements_noop() -> None:
    """Wrap ultralytics.utils.checks.check_requirements as no-op (once)."""
    global _APPLIED
    if _APPLIED:
        return
    apply_airgap_env()
    try:
        from ultralytics.utils import checks as _checks

        _checks.check_requirements = _noop_check_requirements  # type: ignore[method-assign]
        _APPLIED = True
    except Exception as exc:  # noqa: BLE001
        _LOG.info("ultralytics airgap wrap skipped: %s", exc)


def ensure_ultralytics_airgap() -> None:
    """Call before any Ultralytics model import/load."""
    apply_airgap_env()
    install_check_requirements_noop()
