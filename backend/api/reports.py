"""HTML / PDF report download for operator+."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from services.reporter import generate_html_report, generate_pdf_report
from services.security import require_role

router = APIRouter(tags=["reports"])


@router.get("/api/report/html")
async def report_html(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> FileResponse:
    path = await asyncio.to_thread(generate_html_report)
    return FileResponse(
        path,
        media_type="text/html",
        filename=path.name,
    )


@router.get("/api/report/pdf")
async def report_pdf(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> FileResponse:
    path = await asyncio.to_thread(generate_pdf_report)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
    )
