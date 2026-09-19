"""Ollama HTTP proxy + connection manager. Frontend never talks to :11434."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from services.security import BASE_DIR
from services.ollama_discovery import (
    MSG_NO_MODELS,
    MSG_UNAVAILABLE,
    DEFAULT_PORT,
    PROBE_TIMEOUT_SEC,
    base_from_host_port,
    discover_first_healthy,
    error_message,
    normalize_base_url,
    probe_tags,
    scan_lan_ollama,
)
from services.config_utils import safe_bool, safe_int

# Back-compat export for smokes / callers
OLLAMA_BASE = "http://127.0.0.1:11434"
UNAVAILABLE = MSG_UNAVAILABLE
TAGS_TIMEOUT = PROBE_TIMEOUT_SEC
GENERATE_TIMEOUT = 60.0
REPROBE_TTL_SEC = 30.0
STARTUP_LADDER_WALL_SEC = 5.0

CONFIG_DIR = BASE_DIR / "config" / "local"
CONFIG_PATH = CONFIG_DIR / "ollama.json"

_EMBED_HINTS = ("embed", "bge-", "e5-", "minilm", "nomic-embed")
_VISION_HINTS = ("llava", "vision", "-vl", "vl:", "qwen2.5vl", "qwen2vl")
_CODER_HINTS = ("coder", "code")

_lock = threading.RLock()
_state = "disconnected"  # disconnected | searching | connected | degraded
_base_url = ""
_model = ""
_timeout_sec = GENERATE_TIMEOUT
_models: list[dict[str, Any]] = []
_message = ""
_error_kind = ""
_auto_reconnect = True
_reprobe_stop = threading.Event()
_reprobe_thread: threading.Thread | None = None
_startup_started = False
_last_logged_state = ""


def _log(message: str, *, transition: bool = False) -> None:
    from services import runtime_log

    runtime_log.info("ai", message)
    logs = BASE_DIR / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(timezone.utc).isoformat()} {message}\n"
    with (logs / "ai.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _log_transition(new_state: str, detail: str = "") -> None:
    global _last_logged_state
    with _lock:
        if new_state == _last_logged_state and not detail:
            return
        _last_logged_state = new_state
    msg = f"ollama state={new_state}"
    if detail:
        msg = f"{msg} {detail}"
    _log(msg, transition=True)


def _default_config() -> dict[str, Any]:
    return {
        "base_url": "",
        "host": "127.0.0.1",
        "port": DEFAULT_PORT,
        "model": "",
        "timeout_sec": GENERATE_TIMEOUT,
        "auto_reconnect": True,
        "last_ok_at": "",
    }


def load_config() -> dict[str, Any]:
    cfg = _default_config()
    if not CONFIG_PATH.is_file():
        return cfg
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            cfg.update({k: raw[k] for k in cfg if k in raw})
    except (OSError, json.JSONDecodeError):
        pass
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    merged = _default_config()
    merged.update(cfg)
    CONFIG_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_host_port(base: str) -> tuple[str, int]:
    b = normalize_base_url(base)
    if not b:
        return "127.0.0.1", DEFAULT_PORT
    u = urlparse(b)
    host = u.hostname or "127.0.0.1"
    port = int(u.port or DEFAULT_PORT)
    return host, port


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


def _models_from_probe(raw_models: list[Any]) -> list[dict[str, Any]]:
    return _parse_tags_payload({"models": raw_models})


def get_status() -> dict[str, Any]:
    with _lock:
        return {
            "state": _state,
            "base_url": _base_url,
            "host": _parse_host_port(_base_url)[0] if _base_url else load_config().get("host", "127.0.0.1"),
            "port": _parse_host_port(_base_url)[1] if _base_url else int(load_config().get("port") or DEFAULT_PORT),
            "model": _model,
            "timeout_sec": _timeout_sec,
            "models": list(_models),
            "message": _message,
            "error_kind": _error_kind,
            "available": _state in ("connected", "degraded") and bool(_models),
            "auto_reconnect": _auto_reconnect,
        }


def _set_state(
    state: str,
    *,
    base_url: str | None = None,
    models: list[dict[str, Any]] | None = None,
    message: str = "",
    error_kind: str = "",
    model: str | None = None,
) -> None:
    global _state, _base_url, _models, _message, _error_kind, _model, OLLAMA_BASE
    with _lock:
        prev = _state
        _state = state
        if base_url is not None:
            _base_url = base_url
            if base_url:
                OLLAMA_BASE = base_url
        if models is not None:
            _models = models
        _message = message
        _error_kind = error_kind
        if model is not None:
            _model = model
        changed = prev != state
    if changed:
        _log_transition(state, message)


def _stop_reprobe() -> None:
    global _reprobe_thread
    _reprobe_stop.set()
    t = _reprobe_thread
    _reprobe_thread = None
    if t and t.is_alive() and t is not threading.current_thread():
        t.join(timeout=1.0)


def _start_reprobe() -> None:
    global _reprobe_thread
    _stop_reprobe()
    _reprobe_stop.clear()

    def loop() -> None:
        while not _reprobe_stop.wait(REPROBE_TTL_SEC):
            with _lock:
                if _state not in ("connected", "degraded"):
                    break
                base = _base_url
            if not base:
                break
            result = probe_tags(base, timeout=TAGS_TIMEOUT)
            if result["ok"]:
                models = _models_from_probe(result.get("models") or [])
                chat = [m for m in models if not m.get("embed")]
                ranked = _rank_models(chat or models, want_vision=True)
                if not ranked:
                    _set_state(
                        "connected",
                        base_url=base,
                        models=[],
                        message=MSG_NO_MODELS,
                        error_kind="no_models",
                    )
                else:
                    _set_state(
                        "connected",
                        base_url=base,
                        models=ranked,
                        message="",
                        error_kind="",
                    )
            elif result.get("error_kind") == "slow":
                _set_state(
                    "degraded",
                    base_url=base,
                    message=error_message("slow"),
                    error_kind="slow",
                )
            else:
                _set_state(
                    "disconnected",
                    base_url=base,
                    models=[],
                    message=result.get("message") or MSG_UNAVAILABLE,
                    error_kind=str(result.get("error_kind") or "refused"),
                )
                break

    _reprobe_thread = threading.Thread(target=loop, name="ollama-reprobe", daemon=True)
    _reprobe_thread.start()


def _apply_success(base: str, raw_models: list[Any], *, preferred_model: str = "") -> dict[str, Any]:
    models = _models_from_probe(raw_models)
    chat = [m for m in models if not m.get("embed")]
    ranked = _rank_models(chat or models, want_vision=True)
    host, port = _parse_host_port(base)
    chosen = (preferred_model or _model or "").strip()
    names = {m["name"] for m in ranked}
    if chosen and chosen not in names and ranked:
        chosen = str(ranked[0]["name"])
    elif not chosen and ranked:
        chosen = str(ranked[0]["name"])
    kind = ""
    msg = ""
    if not ranked:
        kind = "no_models"
        msg = MSG_NO_MODELS
    _set_state(
        "connected",
        base_url=base,
        models=ranked,
        message=msg,
        error_kind=kind,
        model=chosen,
    )
    cfg = load_config()
    cfg.update(
        {
            "base_url": base,
            "host": host,
            "port": port,
            "model": chosen,
            "timeout_sec": _timeout_sec,
            "auto_reconnect": _auto_reconnect,
            "last_ok_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    save_config(cfg)
    _start_reprobe()
    return get_status()


def connect(
    *,
    base_url: str | None = None,
    host: str | None = None,
    port: int | None = None,
    model: str | None = None,
    timeout_sec: float | None = None,
    use_ladder: bool = True,
) -> dict[str, Any]:
    global _timeout_sec, _model, _auto_reconnect
    if timeout_sec is not None:
        _timeout_sec = float(timeout_sec)
    if model is not None:
        _model = (model or "").strip()

    forced = ""
    if base_url:
        forced = normalize_base_url(base_url)
    elif host:
        forced = base_from_host_port(host, int(port or DEFAULT_PORT))

    _set_state("searching", message="Поиск Ollama…", error_kind="")
    try:
        if forced:
            result = probe_tags(forced, timeout=TAGS_TIMEOUT)
            if result["ok"]:
                return _apply_success(forced, result.get("models") or [], preferred_model=_model)
            _set_state(
                "disconnected",
                base_url=forced,
                models=[],
                message=result.get("message") or MSG_UNAVAILABLE,
                error_kind=str(result.get("error_kind") or "refused"),
            )
            return get_status()

        if not use_ladder:
            _set_state("disconnected", message=MSG_UNAVAILABLE, error_kind="refused")
            return get_status()

        cfg = load_config()
        result = discover_first_healthy(
            saved_base=str(cfg.get("base_url") or "") or None,
            deadline=None,
            per_probe_timeout=TAGS_TIMEOUT,
        )
        if result.get("ok"):
            return _apply_success(
                str(result["base_url"]),
                result.get("models") or [],
                preferred_model=_model or str(cfg.get("model") or ""),
            )
        _set_state(
            "disconnected",
            models=[],
            message=result.get("message") or MSG_UNAVAILABLE,
            error_kind=str(result.get("error_kind") or "refused"),
        )
        return get_status()
    except Exception as exc:  # noqa: BLE001
        _set_state("disconnected", message=str(exc), error_kind="refused")
        return get_status()


def disconnect() -> dict[str, Any]:
    _stop_reprobe()
    _set_state("disconnected", models=[], message="", error_kind="")
    return get_status()


def save_settings(
    *,
    host: str | None = None,
    port: int | None = None,
    base_url: str | None = None,
    model: str | None = None,
    timeout_sec: float | None = None,
    auto_reconnect: bool | None = None,
    connect_now: bool = True,
) -> dict[str, Any]:
    global _timeout_sec, _auto_reconnect, _model
    cfg = load_config()
    if host is not None:
        cfg["host"] = host.strip()
    if port is not None:
        cfg["port"] = int(port)
    if base_url:
        cfg["base_url"] = normalize_base_url(base_url)
        h, p = _parse_host_port(cfg["base_url"])
        cfg["host"], cfg["port"] = h, p
    elif host is not None:
        cfg["base_url"] = base_from_host_port(cfg["host"], safe_int(cfg.get("port"), DEFAULT_PORT))
    if model is not None:
        cfg["model"] = model.strip()
        _model = cfg["model"]
    if timeout_sec is not None:
        cfg["timeout_sec"] = float(timeout_sec)
        _timeout_sec = float(timeout_sec)
    if auto_reconnect is not None:
        cfg["auto_reconnect"] = bool(auto_reconnect)
        _auto_reconnect = bool(auto_reconnect)
    save_config(cfg)
    if connect_now:
        return connect(
            base_url=str(cfg.get("base_url") or "") or None,
            host=str(cfg.get("host") or "") or None,
            port=safe_int(cfg.get("port"), DEFAULT_PORT),
            model=str(cfg.get("model") or "") or None,
            timeout_sec=float(cfg.get("timeout_sec") or GENERATE_TIMEOUT),
            use_ladder=not bool(cfg.get("base_url")),
        )
    return get_status()


def scan_lan() -> dict[str, Any]:
    hosts = scan_lan_ollama()
    return {"hosts": hosts, "count": len(hosts)}


def startup_reconnect() -> None:
    """Non-blocking: spawn daemon with 5s wall-clock ladder. Never call sync from lifespan yield path except spawn."""
    global _startup_started, _auto_reconnect, _timeout_sec, _model
    with _lock:
        if _startup_started:
            return
        _startup_started = True
    cfg = load_config()
    _auto_reconnect = safe_bool(cfg.get("auto_reconnect"), True)
    _timeout_sec = float(cfg.get("timeout_sec") or GENERATE_TIMEOUT)
    _model = str(cfg.get("model") or "")
    if not _auto_reconnect:
        return
    saved = str(cfg.get("base_url") or "").strip()
    if not saved and not (os_environ_url()):
        # Still allow ladder for loopback/WSL within 5s
        pass

    def run() -> None:
        deadline = time.monotonic() + STARTUP_LADDER_WALL_SEC
        _set_state("searching", message="Автоподключение Ollama…", error_kind="")
        result = discover_first_healthy(
            saved_base=saved or None,
            deadline=deadline,
            per_probe_timeout=TAGS_TIMEOUT,
        )
        if result.get("ok"):
            _apply_success(
                str(result["base_url"]),
                result.get("models") or [],
                preferred_model=_model,
            )
            _log("startup reconnect ok")
        else:
            _set_state(
                "disconnected",
                models=[],
                message="",
                error_kind="",
            )
            _log("startup reconnect skipped/failed")

    threading.Thread(target=run, name="ollama-startup", daemon=True).start()


def os_environ_url() -> str:
    import os

    return (os.environ.get("MURAVEI_OLLAMA_URL") or "").strip()


def _strip_data_url(image: str | None) -> str | None:
    if not image:
        return None
    raw = image.strip()
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    return raw or None


def list_models() -> dict[str, Any]:
    """Compatible wrapper: available only when connected."""
    st = get_status()
    if st["state"] not in ("connected", "degraded"):
        return {
            "available": False,
            "models": [],
            "message": st.get("message") or MSG_UNAVAILABLE,
            "state": st["state"],
            "error_kind": st.get("error_kind") or "",
        }
    models = st.get("models") or []
    if not models:
        return {
            "available": False,
            "models": [],
            "message": MSG_NO_MODELS,
            "state": st["state"],
            "error_kind": "no_models",
        }
    return {
        "available": True,
        "models": models,
        "message": st.get("message") or "",
        "state": st["state"],
        "base_url": st.get("base_url"),
        "error_kind": st.get("error_kind") or "",
    }


def generate(
    prompt: str,
    model: str | None = None,
    image_base64: str | None = None,
) -> dict[str, Any]:
    catalog = list_models()
    if not catalog["available"] or not catalog["models"]:
        return {
            "ok": False,
            "status": 503,
            "message": catalog.get("message") or MSG_UNAVAILABLE,
            "analysis": "",
        }
    with _lock:
        base = _base_url
        gen_timeout = _timeout_sec
    if not base:
        return {"ok": False, "status": 503, "message": MSG_UNAVAILABLE, "analysis": ""}

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

    try:
        with httpx.Client(timeout=gen_timeout) as client:
            resp = client.post(f"{base}/api/generate", json=body)
        if resp.status_code != 200:
            _log(f"generate HTTP {resp.status_code} body={resp.text[:300]}")
            return {"ok": False, "status": 503, "message": MSG_UNAVAILABLE, "analysis": ""}
        data = resp.json() or {}
        text = str(data.get("response") or "").strip()
        if not text:
            _log("generate empty response")
            return {"ok": False, "status": 503, "message": MSG_UNAVAILABLE, "analysis": ""}
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
        _set_state("degraded", base_url=base, message=error_message("slow"), error_kind="slow")
        return {"ok": False, "status": 503, "message": error_message("slow"), "analysis": ""}
    except Exception as exc:  # noqa: BLE001
        _log(f"generate error: {exc}")
        return {"ok": False, "status": 503, "message": MSG_UNAVAILABLE, "analysis": ""}


def reset_for_tests() -> None:
    """Test helper: clear in-memory state (does not delete config file)."""
    global _startup_started, _last_logged_state
    _stop_reprobe()
    with _lock:
        _startup_started = False
        _last_logged_state = ""
    _set_state("disconnected", base_url="", models=[], message="", error_kind="", model="")
