"""Ollama endpoint discovery: ladder + WSL cross-namespace + explicit LAN scan."""
from __future__ import annotations

import concurrent.futures
import ipaddress
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from typing import Any
from urllib.parse import urlparse

import httpx

DEFAULT_PORT = 11434
PROBE_TIMEOUT_SEC = 5.0
LAN_TCP_TIMEOUT_SEC = 0.3
LAN_WALL_SEC = 10.0
LAN_MAX_HOSTS = 256

MSG_REFUSED = "Соединение отклонено (Ollama не слушает этот адрес)"
MSG_WRONG_SERVICE = (
    "Порт 11434 занят другим сервисом, проверьте MURAVEI_OLLAMA_URL"
)
MSG_SLOW = "Долгий ответ Ollama (холодный старт) — подождите"
MSG_NO_MODELS = "Нет моделей. Выполните: ollama pull qwen2.5vl:7b"
MSG_CORS = "Возможна проблема CORS — проверьте URL Ollama"
MSG_UNAVAILABLE = (
    "Ollama не подключена. Откройте AI-анализ → Подключить "
    "или задайте MURAVEI_OLLAMA_URL"
)


def normalize_base_url(url: str) -> str:
    raw = (url or "").strip().rstrip("/")
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "http://" + raw
    return raw.rstrip("/")


def base_from_host_port(host: str, port: int = DEFAULT_PORT) -> str:
    h = (host or "").strip()
    if not h:
        return ""
    if ":" in h and not h.startswith("["):
        # IPv6 without brackets
        h = f"[{h}]"
    return normalize_base_url(f"http://{h}:{int(port)}")


def is_ollama_tags_payload(payload: Any) -> bool:
    """True if JSON looks like Ollama /api/tags (models key is a list, or empty object OK)."""
    if not isinstance(payload, dict):
        return False
    if "models" not in payload:
        # Some builds return {} briefly — treat as Ollama-shaped if no foreign keys dominate
        return True
    return isinstance(payload.get("models"), list)


def classify_probe_error(
    *,
    status_code: int | None = None,
    exc: BaseException | None = None,
    body_text: str = "",
    is_json: bool = False,
    payload: Any = None,
) -> str:
    """Return error_kind: refused | wrong_service | slow | cors | no_models."""
    if exc is not None:
        name = type(exc).__name__.lower()
        msg = str(exc).lower()
        if "timeout" in name or "timeout" in msg:
            return "slow"
        if "cors" in msg:
            return "cors"
        return "refused"
    if status_code is not None and status_code != 200:
        return "wrong_service"
    if not is_json:
        return "wrong_service"
    if payload is not None and not is_ollama_tags_payload(payload):
        return "wrong_service"
    return "refused"


def error_message(kind: str) -> str:
    return {
        "refused": MSG_REFUSED,
        "wrong_service": MSG_WRONG_SERVICE,
        "slow": MSG_SLOW,
        "no_models": MSG_NO_MODELS,
        "cors": MSG_CORS,
    }.get(kind, MSG_UNAVAILABLE)


def probe_tags(
    base_url: str,
    *,
    timeout: float = PROBE_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Probe GET {base}/api/tags. Returns ok/models/error_kind/message/elapsed_ms."""
    base = normalize_base_url(base_url)
    out: dict[str, Any] = {
        "ok": False,
        "base_url": base,
        "models": [],
        "error_kind": "refused",
        "message": MSG_REFUSED,
        "elapsed_ms": 0,
        "status_code": None,
    }
    if not base:
        return out
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{base}/api/tags")
        out["status_code"] = resp.status_code
        out["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        if resp.status_code != 200:
            kind = classify_probe_error(status_code=resp.status_code, body_text=resp.text[:200])
            out["error_kind"] = kind
            out["message"] = error_message(kind)
            return out
        try:
            payload = resp.json()
            is_json = True
        except Exception:  # noqa: BLE001
            payload = None
            is_json = False
        if not is_json or not is_ollama_tags_payload(payload):
            kind = "wrong_service"
            out["error_kind"] = kind
            out["message"] = error_message(kind)
            return out
        models = []
        for item in (payload or {}).get("models") or []:
            name = str(item.get("name") or "")
            if name:
                models.append(item)
        out["ok"] = True
        out["models"] = models
        out["error_kind"] = ""
        out["message"] = ""
        if not models:
            out["error_kind"] = "no_models"
            out["message"] = MSG_NO_MODELS
            # Still "ok" transport-wise — caller decides
        return out
    except httpx.TimeoutException as exc:
        out["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        out["error_kind"] = "slow"
        out["message"] = error_message("slow")
        out["_exc"] = str(exc)
        return out
    except Exception as exc:  # noqa: BLE001
        out["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        kind = classify_probe_error(exc=exc)
        out["error_kind"] = kind
        out["message"] = error_message(kind)
        return out


def _inside_wsl() -> bool:
    if platform.system() != "Linux":
        return False
    try:
        ver = Path_read("/proc/version")
        return "microsoft" in ver.lower() or "wsl" in ver.lower()
    except OSError:
        return False


def Path_read(path: str) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8", errors="replace")


def _wsl_gateway_candidates() -> list[str]:
    """When inside WSL: Windows host via default gateway."""
    bases: list[str] = []
    try:
        out = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        m = re.search(r"via\s+(\d+\.\d+\.\d+\.\d+)", out.stdout or "")
        if m:
            bases.append(base_from_host_port(m.group(1)))
    except Exception:  # noqa: BLE001
        pass
    if not bases:
        try:
            # /proc/net/route: destination 00000000 = default
            for line in Path_read("/proc/net/route").splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 3 and parts[1] == "00000000":
                    gw_hex = parts[2]
                    # little-endian hex
                    b = bytes.fromhex(gw_hex)
                    ip = ".".join(str(x) for x in reversed(b))
                    bases.append(base_from_host_port(ip))
                    break
        except Exception:  # noqa: BLE001
            pass
    return bases


def _windows_wsl_instance_candidates() -> list[str]:
    """On Windows: IPs of WSL distros."""
    if os.name != "nt":
        return []
    wsl = shutil.which("wsl") or shutil.which("wsl.exe")
    if not wsl:
        return []
    bases: list[str] = []
    try:
        proc = subprocess.run(
            [wsl, "--", "ip", "-4", "-o", "addr", "show", "scope", "global"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        for line in (proc.stdout or "").splitlines():
            m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/\d+", line)
            if m:
                bases.append(base_from_host_port(m.group(1)))
    except Exception:  # noqa: BLE001
        pass
    return bases


def ladder_candidates(*, saved_base: str | None = None) -> list[str]:
    """Ordered unique candidate base URLs."""
    seen: set[str] = set()
    out: list[str] = []

    def add(url: str) -> None:
        b = normalize_base_url(url)
        if b and b not in seen:
            seen.add(b)
            out.append(b)

    env = (os.environ.get("MURAVEI_OLLAMA_URL") or "").strip()
    if env:
        add(env)
    add("http://127.0.0.1:11434")
    add("http://[::1]:11434")
    try:
        if _inside_wsl():
            for b in _wsl_gateway_candidates():
                add(b)
        else:
            for b in _windows_wsl_instance_candidates():
                add(b)
    except Exception:  # noqa: BLE001
        pass
    if saved_base:
        add(saved_base)
    return out


def discover_first_healthy(
    *,
    saved_base: str | None = None,
    deadline: float | None = None,
    per_probe_timeout: float = PROBE_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Walk ladder until healthy tags. Respects optional wall-clock deadline (epoch seconds)."""
    last: dict[str, Any] = {
        "ok": False,
        "base_url": "",
        "models": [],
        "error_kind": "refused",
        "message": MSG_UNAVAILABLE,
        "tried": [],
    }
    for base in ladder_candidates(saved_base=saved_base):
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0.05:
                last["error_kind"] = "slow"
                last["message"] = "Поиск Ollama прерван по таймауту"
                break
            timeout = min(per_probe_timeout, remaining)
        else:
            timeout = per_probe_timeout
        result = probe_tags(base, timeout=timeout)
        last["tried"].append({"base_url": base, "ok": result["ok"], "error_kind": result.get("error_kind")})
        if result["ok"]:
            return result
        last = {**result, "tried": last["tried"]}
    return last


def _local_ipv4_networks() -> list[ipaddress.IPv4Network]:
    nets: list[ipaddress.IPv4Network] = []
    try:
        import psutil

        for _name, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if getattr(a, "family", None) != socket.AF_INET:
                    continue
                ip = getattr(a, "address", None)
                if not ip or ip.startswith("127."):
                    continue
                try:
                    nets.append(ipaddress.IPv4Network(f"{ip}/24", strict=False))
                except ValueError:
                    continue
    except Exception:  # noqa: BLE001
        pass
    return nets


def _tcp_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def scan_lan_ollama(
    *,
    port: int = DEFAULT_PORT,
    wall_sec: float = LAN_WALL_SEC,
    tcp_timeout: float = LAN_TCP_TIMEOUT_SEC,
) -> list[dict[str, Any]]:
    """Explicit LAN scan: TCP probe :11434 on local /24. Never call on startup."""
    deadline = time.monotonic() + wall_sec
    hosts: list[str] = []
    for net in _local_ipv4_networks():
        for host in net.hosts():
            hosts.append(str(host))
            if len(hosts) >= LAN_MAX_HOSTS:
                break
        if len(hosts) >= LAN_MAX_HOSTS:
            break

    found: list[dict[str, Any]] = []
    if not hosts:
        return found

    def check(h: str) -> dict[str, Any] | None:
        if time.monotonic() > deadline:
            return None
        if not _tcp_open(h, port, tcp_timeout):
            return None
        base = base_from_host_port(h, port)
        # Optional light tags probe with tiny remaining budget
        rem = max(0.2, deadline - time.monotonic())
        tags = probe_tags(base, timeout=min(1.5, rem))
        return {
            "host": h,
            "port": port,
            "base_url": base,
            "ok": bool(tags.get("ok")),
            "error_kind": tags.get("error_kind") or "",
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        futs = {pool.submit(check, h): h for h in hosts}
        try:
            for fut in concurrent.futures.as_completed(futs, timeout=wall_sec):
                if time.monotonic() > deadline:
                    break
                try:
                    row = fut.result()
                except Exception:  # noqa: BLE001
                    continue
                if row and (row.get("ok") or row.get("base_url")):
                    # Include TCP-open hosts even if tags failed (picker)
                    if _tcp_open(row["host"], port, 0.15) or row.get("ok"):
                        found.append(row)
        except concurrent.futures.TimeoutError:
            pass
    # Prefer ok=True first, unique hosts
    uniq: dict[str, dict[str, Any]] = {}
    for row in found:
        uniq[row["host"]] = row
    ordered = sorted(uniq.values(), key=lambda r: (not r.get("ok"), r["host"]))
    return ordered
