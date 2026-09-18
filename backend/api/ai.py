"""AI routes: Ollama proxied through the backend only."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config import GENERATE_TIMEOUT
from services.ai_crops import detection_crop_b64
from services.autolabel import parse_autolabel_result
from services.classes import get_class_catalog
from services.ollama_proxy import (
    UNAVAILABLE,
    connect as ollama_connect,
    disconnect as ollama_disconnect,
    generate,
    get_status as ollama_status,
    list_models,
    save_settings as ollama_save_settings,
    scan_lan as ollama_scan_lan,
)
from services.security import require_role

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Rate limiting: max 2 concurrent Ollama requests to prevent overload
_ollama_semaphore = asyncio.Semaphore(2)


def _sanitize_prompt(prompt: str) -> str:
    """Escape HTML/special chars to prevent prompt injection."""
    return (
        prompt.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


class AnalyzeRequest(BaseModel):
    prompt: str = Field(default="")
    model: str | None = None
    image_base64: str | None = None
    detection_id: str | None = None
    video_path: str | None = None
    time_sec: float | None = None


class AutolabelRequest(BaseModel):
    detection_id: str
    model: str | None = None


class OllamaConnectBody(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    base_url: str | None = None
    model: str | None = None
    timeout_sec: float | None = Field(default=None, ge=5, le=600)


class OllamaSettingsBody(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    base_url: str | None = None
    model: str | None = None
    timeout_sec: float | None = Field(default=None, ge=5, le=600)
    auto_reconnect: bool | None = None
    connect_now: bool = True


_VISION_PROMPT_PREFIX = (
    "На приложенном кадре (crop детекции) опиши, что видно: форма, цвет, "
    "материал, окружение. Затем сравни с метками YOLO/оператора.\n\n"
)


@router.get("/ollama/status")
async def ai_ollama_status(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return await asyncio.to_thread(ollama_status)


@router.post("/ollama/connect")
async def ai_ollama_connect(
    body: OllamaConnectBody | None = None,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    body = body or OllamaConnectBody()
    return await asyncio.to_thread(
        ollama_connect,
        base_url=body.base_url,
        host=body.host,
        port=body.port,
        model=body.model,
        timeout_sec=body.timeout_sec,
        use_ladder=not bool((body.base_url or body.host or "").strip()),
    )


@router.post("/ollama/disconnect")
async def ai_ollama_disconnect(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return await asyncio.to_thread(ollama_disconnect)


@router.post("/ollama/scan")
async def ai_ollama_scan(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return await asyncio.to_thread(ollama_scan_lan)


@router.put("/ollama/settings")
async def ai_ollama_settings(
    body: OllamaSettingsBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return await asyncio.to_thread(
        ollama_save_settings,
        host=body.host,
        port=body.port,
        base_url=body.base_url,
        model=body.model,
        timeout_sec=body.timeout_sec,
        auto_reconnect=body.auto_reconnect,
        connect_now=body.connect_now,
    )


@router.get("/models")
async def ai_models(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, Any]:
    return await asyncio.to_thread(list_models)


@router.post("/analyze")
async def ai_analyze(
    body: AnalyzeRequest,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    image = (body.image_base64 or "").strip() or None
    if not image and body.detection_id:
        image = await asyncio.to_thread(detection_crop_b64, body.detection_id)
    if not image and body.video_path and body.time_sec is not None:
        from services.ai_crops import video_frame_b64

        image = await asyncio.to_thread(video_frame_b64, body.video_path, float(body.time_sec))
    prompt = (body.prompt or "").strip()
    if not prompt:
        prompt = (
            "Ты аналитик разведки. По изображению опиши объект: что видно, "
            "признаки, что проверить. Без выдуманных фактов."
        )
    else:
        prompt = _sanitize_prompt(prompt)
    if image and _VISION_PROMPT_PREFIX not in prompt:
        prompt = _VISION_PROMPT_PREFIX + prompt
    if not image:
        prompt = (
            "[Изображение не передано — опиши только по тексту меток и укажи, "
            "что нужен кроп для визуального анализа.]\n\n"
            + prompt
        )
    timeout = (body.timeout_sec or GENERATE_TIMEOUT)
    async with _ollama_semaphore:
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    generate,
                    prompt=prompt,
                    model=body.model,
                    image_base64=image,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=408, detail="Request timeout")
    if not result["ok"]:
        raise HTTPException(status_code=int(result["status"]), detail=result["message"] or UNAVAILABLE)
    return {
        "status": "ok",
        "analysis": result["analysis"],
        "model": result.get("model"),
        "provider": result.get("provider"),
        "had_image": bool(image),
    }


@router.post("/autolabel")
async def ai_autolabel(
    body: AutolabelRequest,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    image = await asyncio.to_thread(detection_crop_b64, body.detection_id)
    if not image:
        raise HTTPException(status_code=404, detail="Кроп детекции не найден")

    catalog = [item for item in get_class_catalog() if item.get("enabled", True)]
    compact_catalog = [
        {
            "id": int(item["id"]),
            "name_en": str(item["name_en"]),
            "name_ru": str(item.get("name_ru") or ""),
        }
        for item in catalog
    ]
    prompt = (
        "Выбери ровно один наиболее подходящий класс для объекта на кропе из каталога ниже. "
        "Верни только JSON без markdown: "
        '{"class_id": integer, "confidence": number 0..1, "reason": "кратко"}. '
        "Не придумывай class_id вне каталога.\nCATALOG="
        + json.dumps(compact_catalog, ensure_ascii=False, separators=(",", ":"))
    )
    async with _ollama_semaphore:
        result = await asyncio.to_thread(
            generate,
            prompt=prompt,
            model=body.model,
            image_base64=image,
        )
    if not result["ok"]:
        raise HTTPException(
            status_code=int(result["status"]),
            detail=result["message"] or UNAVAILABLE,
        )

    try:
        proposal = parse_autolabel_result(str(result.get("analysis") or ""), catalog)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Ollama вернула невалидный JSON") from exc
    return {
        "status": "ok",
        "proposal": proposal,
        "model": result.get("model"),
    }
