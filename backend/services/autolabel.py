"""Pure helpers for catalog-scoped Ollama autolabel responses."""
from __future__ import annotations

import json
import re
from typing import Any


def parse_autolabel_result(raw: str, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    match = re.search(r"\{.*\}", raw.strip(), flags=re.DOTALL)
    try:
        parsed = json.loads(match.group(0) if match else raw)
        class_id = int(parsed["class_id"])
        confidence = max(0.0, min(1.0, float(parsed.get("confidence") or 0)))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("invalid Ollama autolabel JSON") from exc
    item = next((candidate for candidate in catalog if int(candidate["id"]) == class_id), None)
    if item is None:
        raise ValueError("class_id outside catalog")
    return {
        "class_id": class_id,
        "class_name": str(item["name_en"]),
        "name_ru": str(item.get("name_ru") or ""),
        "confidence": confidence,
        "reason": str(parsed.get("reason") or ""),
    }
