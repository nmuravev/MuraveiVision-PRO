"""Class dictionary overrides API (engineer+)."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.classes import get_class_catalog, invalidate_class_cache, live_prompt_names
from services.db import (
    delete_class_override,
    delete_excluded_class,
    get_class_override,
    list_class_overrides,
    list_excluded_classes,
    upsert_class_override,
    upsert_excluded_class,
)
from services.security import require_role

router = APIRouter(prefix="/api/classes", tags=["classes"])


class OverridePatch(BaseModel):
    name_ru: str | None = Field(default=None, max_length=200)
    aliases: list[str] | None = None
    enabled: bool | None = None
    in_prompt: bool | None = None
    confidence_threshold: float | None = Field(default=None, ge=0.01, le=1.0)
    clear_confidence_threshold: bool = False


def _normalize_aliases(aliases: list[str] | None) -> str:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in aliases or []:
        key = str(raw).strip().lower().replace("_", " ")
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(key)
    return json.dumps(cleaned, ensure_ascii=False)


@router.get("/catalog")
async def classes_catalog(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return {
        "classes": get_class_catalog(),
        "live_prompts": live_prompt_names(),
    }


@router.get("/overrides")
async def classes_overrides(
    _user: dict[str, Any] = Depends(require_role("engineer")),
) -> dict[str, Any]:
    return {"overrides": list_class_overrides()}


@router.put("/overrides/{class_id}")
async def classes_override_put(
    class_id: int,
    body: OverridePatch,
    _user: dict[str, Any] = Depends(require_role("engineer")),
) -> dict[str, Any]:
    catalog_ids = {int(c["id"]) for c in get_class_catalog()}
    # Allow put even if catalog cached without this id after yaml change — still validate range
    if class_id < 0 or (catalog_ids and class_id not in catalog_ids and get_class_override(class_id) is None):
        # soft check: class must exist in yaml catalog
        raw_ids = {int(c["id"]) for c in get_class_catalog()}
        if class_id not in raw_ids:
            raise HTTPException(status_code=404, detail=f"unknown class_id={class_id}")
    aliases_json = _normalize_aliases(body.aliases) if body.aliases is not None else None
    row = upsert_class_override(
        class_id,
        name_ru=body.name_ru,
        aliases=aliases_json,
        enabled=body.enabled,
        in_prompt=body.in_prompt,
        confidence_threshold=body.confidence_threshold,
        clear_confidence_threshold=body.clear_confidence_threshold,
    )
    invalidate_class_cache()
    try:
        from services.response_validator import get_validator

        get_validator().refresh_catalog()
    except Exception as exc:  # noqa: BLE001
        print(f"[CLASSES] validator refresh failed: {exc}")
    return {"ok": True, "override": row, "classes": get_class_catalog()}


@router.delete("/overrides/{class_id}")
async def classes_override_delete(
    class_id: int,
    _user: dict[str, Any] = Depends(require_role("engineer")),
) -> dict[str, Any]:
    deleted = delete_class_override(class_id)
    invalidate_class_cache()
    try:
        from services.response_validator import get_validator

        get_validator().refresh_catalog()
    except Exception as exc:  # noqa: BLE001
        print(f"[CLASSES] validator refresh failed: {exc}")
    return {"ok": True, "deleted": deleted, "classes": get_class_catalog()}


# ─── Excluded classes API ───────────────────────────────────────────


class ExcludedClassBody(BaseModel):
    class_name: str = Field(min_length=1, max_length=100)


@router.get("/excluded")
async def classes_excluded(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    """List all excluded classes (COCO DROP + operator additions)."""
    return {"excluded": list_excluded_classes()}


@router.post("/excluded")
async def classes_excluded_add(
    body: ExcludedClassBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    """Add a class to exclusion list."""
    row = upsert_excluded_class(body.class_name)
    invalidate_class_cache()
    try:
        from services.classes import invalidate_excluded_cache

        invalidate_excluded_cache()
    except Exception as exc:  # noqa: BLE001
        print(f"[CLASSES] excluded cache invalidation failed: {exc}")
    return {"ok": True, "excluded_class": row}


@router.delete("/excluded/{class_name}")
async def classes_excluded_delete(
    class_name: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    """Remove a class from exclusion list."""
    deleted = delete_excluded_class(class_name)
    try:
        from services.classes import invalidate_excluded_cache

        invalidate_excluded_cache()
    except Exception as exc:  # noqa: BLE001
        print(f"[CLASSES] excluded cache invalidation failed: {exc}")
    return {"ok": True, "deleted": deleted}
