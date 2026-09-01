"""AI routes: Ollama proxied through the backend only."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.ai_crops import detection_crop_b64
from services.autolabel import parse_autolabel_result
from services.classes import get_class_catalog
from services.ollama_proxy import UNAVAILABLE, generate, list_models
from services.security import require_role

router = APIRouter(prefix="/api/ai", tags=["ai"])


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


_VISION_PROMPT_PREFIX = (
    "На приложенном кадре (crop детекции) опиши, что видно: форма, цвет, "
    "материал, окружение. Затем сравни с метками YOLO/оператора.\n\n"
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
    if image and _VISION_PROMPT_PREFIX not in prompt:
        prompt = _VISION_PROMPT_PREFIX + prompt
    if not image:
        prompt = (
            "[Изображение не передано — опиши только по тексту меток и укажи, "
            "что нужен кроп для визуального анализа.]\n\n"
            + prompt
        )
    result = await asyncio.to_thread(
        generate,
        prompt=prompt,
        model=body.model,
        image_base64=image,
    )
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
