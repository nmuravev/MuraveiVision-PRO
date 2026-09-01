"""Ollama HTTP proxy. Frontend never talks to :11434."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from main import BASE_DIR

OLLAMA_BASE = "http://127.0.0.1:11434"
TAGS_TIMEOUT = 5.0
GENERATE_TIMEOUT = 60.0
TAGS_RETRIES = 3
TAGS_RETRY_DELAY_SEC = 2.0
GENERATE_CONNECT_RETRIES = 2
GENERATE_RETRY_DELAY_SEC = 2.0
UNAVAILABLE = (
    "Ollama не запущена. Проверьте ollama/ollama.exe "
    "(Full Kit) или системный Ollama на 127.0.0.1:11434"
)

_EMBED_HINTS = ("embed", "bge-", "e5-", "minilm", "nomic-embed")
_VISION_HINTS = ("llava", "vision", "-vl", "vl:", "qwen2.5vl", "qwen2vl")
_CODER_HINTS = ("coder", "code")


def _log(message: str) -> None:
    from services import runtime_log

    runtime_log.info("ai", message)
    logs = BASE_DIR / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(timezone.utc).isoformat()} {message}\n"
    with (logs / "ai.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _strip_data_url(image: str | None) -> str | None:
    if not image:
        return None
    raw = image.strip()
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    return raw or None


def _is_embed(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in _EMBED_HINTS)


def _is_vision(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in _VISION_HINTS)


def _is_coder(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in _CODER_HINTS)


def _rank_models(models: list[dict[str, Any]], *, want_vision: bool) -> list[dict[str, Any]]:
    """Prefer chat models; vision first only when an image is attached."""

    def key(m: dict[str, Any]) -> tuple:
        name = str(m["name"])
        return (
            1 if _is_embed(name) else 0,
            0 if (want_vision and _is_vision(name)) else 1 if want_vision else (1 if _is_vision(name) else 0),
            1 if _is_coder(name) else 0,
            float(m.get("sizeMb") or 0),
        )

    return sorted(models, key=key)


def _parse_tags_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    for item in payload.get("models") or []:
        name = str(item.get("name") or "")
        if not name:
            continue
        models.append(
            {
                "name": name,
                "sizeMb": round(float(item.get("size") or 0) / (1024 * 1024), 1),
                "modified": item.get("modified_at") or "",
                "vision": _is_vision(name),
                "embed": _is_embed(name),
            }
        )
    return models


def list_models() -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(1, TAGS_RETRIES + 1):
        try:
            with httpx.Client(timeout=TAGS_TIMEOUT) as client:
                resp = client.get(f"{OLLAMA_BASE}/api/tags")
            if resp.status_code != 200:
                _log(f"tags HTTP {resp.status_code} attempt={attempt}/{TAGS_RETRIES}")
                last_exc = RuntimeError(f"HTTP {resp.status_code}")
            else:
                payload = resp.json() or {}
                models = _parse_tags_payload(payload)
                chat = [m for m in models if not m.get("embed")]
                ranked = _rank_models(chat or models, want_vision=True)
                if not ranked:
                    _log(f"tags empty models attempt={attempt}/{TAGS_RETRIES}")
                else:
                    if attempt > 1:
                        _log(f"tags ok after retry attempt={attempt}")
                    return {"available": True, "models": ranked, "message": ""}
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _log(f"tags error attempt={attempt}/{TAGS_RETRIES}: {exc}")
        if attempt < TAGS_RETRIES:
            time.sleep(TAGS_RETRY_DELAY_SEC)
    if last_exc:
        _log(f"tags unavailable: {last_exc}")
    return {"available": False, "models": [], "message": UNAVAILABLE}


def generate(
    prompt: str,
    model: str | None = None,
    image_base64: str | None = None,
) -> dict[str, Any]:
    catalog = list_models()
    if not catalog["available"] or not catalog["models"]:
        return {"ok": False, "status": 503, "message": UNAVAILABLE, "analysis": ""}
    image = _strip_data_url(image_base64)
    pool = [m for m in catalog["models"] if not m.get("embed")] or catalog["models"]
    ranked = _rank_models(pool, want_vision=bool(image))
    chosen = (model or "").strip() or str(ranked[0]["name"])
    names = {m["name"] for m in catalog["models"]}
    if chosen not in names:
        prefix = [n for n in names if n.startswith(chosen) or chosen.startswith(n.split(":")[0])]
        if prefix:
            chosen = prefix[0]
        else:
            chosen = str(ranked[0]["name"])
    body: dict[str, Any] = {
        "model": chosen,
        "prompt": prompt or "Опиши военные объекты на кадре кратко, по делу.",
        "stream": False,
    }
    if image and not _is_vision(chosen):
        vision_pool = [m for m in catalog["models"] if _is_vision(m["name"]) and not m.get("embed")]
        if vision_pool:
            chosen = str(_rank_models(vision_pool, want_vision=True)[0]["name"])
            body["model"] = chosen
            _log(f"generate switched to vision model={chosen}")
    if image:
        body["images"] = [image]
    _log(f"generate model={chosen} prompt_len={len(body['prompt'])} image={bool(image)}")

    last_exc: Exception | None = None
    for attempt in range(1, GENERATE_CONNECT_RETRIES + 1):
        try:
            with httpx.Client(timeout=GENERATE_TIMEOUT) as client:
                resp = client.post(f"{OLLAMA_BASE}/api/generate", json=body)
            if resp.status_code != 200:
                _log(f"generate HTTP {resp.status_code} body={resp.text[:300]}")
                return {"ok": False, "status": 503, "message": UNAVAILABLE, "analysis": ""}
            data = resp.json() or {}
            text = str(data.get("response") or "").strip()
            if not text:
                _log("generate empty response")
                return {"ok": False, "status": 503, "message": UNAVAILABLE, "analysis": ""}
            _log(f"generate ok chars={len(text)}")
            return {
                "ok": True,
                "status": 200,
                "message": "",
                "analysis": text,
                "model": chosen,
                "provider": "Ollama",
            }
        except httpx.TimeoutException as exc:
            _log(f"generate timeout: {exc}")
            return {"ok": False, "status": 503, "message": UNAVAILABLE, "analysis": ""}
        except httpx.RequestError as exc:
            last_exc = exc
            _log(f"generate connect attempt={attempt}/{GENERATE_CONNECT_RETRIES}: {exc}")
            if attempt < GENERATE_CONNECT_RETRIES:
                time.sleep(GENERATE_RETRY_DELAY_SEC)
                continue
        except Exception as exc:  # noqa: BLE001
            _log(f"generate error: {exc}")
            return {"ok": False, "status": 503, "message": UNAVAILABLE, "analysis": ""}
    _log(f"generate unavailable: {last_exc}")
    return {"ok": False, "status": 503, "message": UNAVAILABLE, "analysis": ""}
