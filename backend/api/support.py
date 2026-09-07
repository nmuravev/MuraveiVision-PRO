"""Operator support diagnostic ZIP (no PINs)."""
from __future__ import annotations

import asyncio
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from config import BASE_DIR
from services.hardware import hardware_spec
from services.security import require_role

router = APIRouter(prefix="/api/support", tags=["support"])

LOGS_DIR = BASE_DIR / "logs"


def _tail(path: Path, max_bytes: int = 256_000) -> str:
    try:
        data = path.read_bytes()
        if len(data) > max_bytes:
            data = data[-max_bytes:]
        return data.decode("utf-8", errors="replace")
    except OSError as exc:
        return f"(cannot read {path.name}: {exc})"


def _last_errors(logs_dir: Path) -> list[str]:
    hits: list[str] = []
    if not logs_dir.is_dir():
        return hits
    keys = ("error", "traceback", "exception", "failed", "unavailable")
    for log_file in sorted(logs_dir.glob("*")):
        if not log_file.is_file():
            continue
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines[-400:]:
            blob = line.lower()
            if any(k in blob for k in keys):
                hits.append(f"{log_file.name}: {line}")
    return hits[-80:]


def _build_diagnostic_zip() -> tuple[bytes, list[str]]:
    hw = hardware_spec()
    errors = _last_errors(LOGS_DIR)
    report_txt = "\n".join(
        [
            "MuraveiVision PRO — diagnostic report",
            f"utc: {datetime.now(timezone.utc).isoformat()}",
            f"platform: {hw.get('platform')}",
            f"cpu: {hw.get('processor')} x{hw.get('cpu_count')}",
            f"ram_mb: {hw.get('ram_total_mb')} (free {hw.get('ram_available_mb')})",
            f"gpu: {hw.get('gpu')}",
            "",
            "Last error-like log lines:",
            *(errors or ["(none found in logs/)"]),
            "",
            "PIN codes are NOT included.",
            "",
        ]
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("hardware_specs.json", json.dumps(hw, ensure_ascii=False, indent=2))
        zf.writestr("error_dump.json", json.dumps(errors, ensure_ascii=False, indent=2))
        zf.writestr("diagnostic_report.txt", report_txt)
        zf.writestr(
            "system_info.json",
            json.dumps(
                {
                    "python": hw.get("python"),
                    "platform": hw.get("platform"),
                    "base_dir": str(BASE_DIR),
                    "captured_at": hw.get("captured_at"),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        if LOGS_DIR.is_dir():
            for log_file in LOGS_DIR.glob("*"):
                if log_file.is_file() and log_file.stat().st_size < 8_000_000:
                    zf.writestr(f"logs/{log_file.name}", _tail(log_file))
        rec_dir = BASE_DIR / "archive" / "recordings"
        if rec_dir.is_dir():
            listing = [str(p.relative_to(BASE_DIR)) for p in rec_dir.rglob("*.mp4")]
            zf.writestr("recordings_index.txt", "\n".join(listing) + "\n")
    return buf.getvalue(), errors


@router.post("/diagnostic-zip")
async def diagnostic_zip(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> StreamingResponse:
    payload, errors = await asyncio.to_thread(_build_diagnostic_zip)
    filename = f"muravei-diagnostic-{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    print(f"[SUPPORT] diagnostic zip errors={len(errors)}")
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
