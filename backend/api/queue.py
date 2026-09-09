"""Export analysis-queue fragments as ZIP (ffmpeg cut)."""
from __future__ import annotations

import io
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.security import assert_in_archive, require_role

BASE_DIR = Path(__file__).resolve().parents[2]

router = APIRouter(tags=["queue"])


class FragmentIn(BaseModel):
    source: str
    in_sec: float = Field(..., alias="in", ge=0)
    out_sec: float = Field(..., alias="out", gt=0)

    model_config = {"populate_by_name": True}


class QueueZipBody(BaseModel):
    fragments: list[FragmentIn] = Field(..., min_length=1, max_length=50)


def _ffmpeg_bin() -> str | None:
    from services.ffmpeg_util import ffmpeg_bin

    return ffmpeg_bin()



def _cut_fragment(ffmpeg: str, src: Path, dest: Path, start: float, end: float) -> None:
    from services import runtime_log

    duration = max(0.05, float(end) - float(start))
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(src),
        "-t",
        f"{duration:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-y",
        str(dest),
    ]
    proc = runtime_log.logged_run(cmd, "queue", timeout=300)
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size < 64:
        cmd2 = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(src),
            "-t",
            f"{duration:.3f}",
            "-c",
            "copy",
            "-y",
            str(dest),
        ]
        proc2 = runtime_log.logged_run(cmd2, "queue", timeout=120)
        if proc2.returncode != 0 or not dest.is_file():
            err = (proc.stderr or proc2.stderr or "ffmpeg failed").strip()
            raise RuntimeError(err[:400])


@router.post("/api/export/queue-zip")
async def export_queue_zip(
    body: QueueZipBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> StreamingResponse:
    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        raise HTTPException(
            status_code=503,
            detail="ffmpeg не найден. Положите ffmpeg.exe в assets/ или добавьте в PATH.",
        )

    meta: list[dict[str, Any]] = []
    buf = io.BytesIO()

    with tempfile.TemporaryDirectory(prefix="muravei_queue_") as tmp:
        tmp_path = Path(tmp)
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()

        for i, frag in enumerate(body.fragments, start=1):
            if frag.out_sec <= frag.in_sec:
                raise HTTPException(
                    status_code=400,
                    detail=f"Фрагмент #{i}: out должен быть больше in",
                )
            try:
                src = assert_in_archive(frag.source)
            except HTTPException:
                raise
            if not src.is_file():
                raise HTTPException(status_code=404, detail=f"Файл не найден: {frag.source}")

            stem = src.stem[:40]
            out_name = f"{i:02d}_{stem}_{frag.in_sec:.2f}-{frag.out_sec:.2f}.mp4"
            dest = clips_dir / out_name
            try:
                _cut_fragment(ffmpeg, src, dest, frag.in_sec, frag.out_sec)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=500,
                    detail=f"Нарезка #{i} не удалась: {exc}",
                ) from exc

            meta.append(
                {
                    "index": i,
                    "source": frag.source,
                    "in": frag.in_sec,
                    "out": frag.out_sec,
                    "duration": frag.out_sec - frag.in_sec,
                    "clip": f"clips/{out_name}",
                }
            )

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "queue_manifest.json",
                json.dumps(
                    {
                        "created": datetime.now(timezone.utc).isoformat(),
                        "count": len(meta),
                        "fragments": meta,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            zf.writestr(
                "README.txt",
                "\n".join(
                    [
                        "MuraveiVision PRO — экспорт очереди фрагментов",
                        "clips/ — нарезанные куски видео (In/Out)",
                        "queue_manifest.json — таймкоды и исходные пути",
                        "PIN-коды в архив не входят.",
                        "",
                    ]
                ),
            )
            for clip in sorted(clips_dir.glob("*.mp4")):
                zf.write(clip, f"clips/{clip.name}")

    buf.seek(0)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"muravei-queue-{stamp}.zip"
    print(f"[QUEUE] export zip fragments={len(body.fragments)} → {filename}")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
