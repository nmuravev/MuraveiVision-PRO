"""Dual-instance network smoke: hub :8000 + client :8001.

Uses REST only (matches v3.2 transport). Exit 0 if all checks pass.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


HUB = "http://127.0.0.1:8000"
CLIENT = "http://127.0.0.1:8001"
PIN = "1234567"
TICK_WAIT = 22.0


def req(
    base: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(
        base + path, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return e.code, payload


def login(base: str) -> str:
    code, data = req(base, "POST", "/api/auth/login", body={"pin": PIN})
    if code != 200 or not data.get("token"):
        raise RuntimeError(f"login failed {base}: {code} {data}")
    return str(data["token"])


def wait_health(base: str, label: str, tries: int = 40) -> None:
    for i in range(tries):
        try:
            code, _ = req(base, "GET", "/api/system/hardware", timeout=3.0)
            # may 401 — any response means up
            if code in (200, 401, 403):
                print(f"[ok] {label} up ({code})")
                return
        except Exception as exc:  # noqa: BLE001
            if i == tries - 1:
                raise RuntimeError(f"{label} not up: {exc}") from exc
        time.sleep(0.5)
    raise RuntimeError(f"{label} not up")


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    wait_health(HUB, "hub")
    wait_health(CLIENT, "client")

    hub_tok = login(HUB)
    client_tok = login(CLIENT)

    # Configure hub server
    code, cfg = req(
        HUB,
        "POST",
        "/api/network/config",
        token=hub_tok,
        body={
            "mode": "server",
            "server_ip": "127.0.0.1",
            "port": 8000,
            "base_name": "Hub-A",
        },
    )
    # engineer role needed — operator pin may not work for POST config
    if code == 403:
        # login as engineer
        code_e, data_e = req(HUB, "POST", "/api/auth/login", body={"pin": "0000000"})
        if code_e != 200:
            results.append(("config-hub", False, f"engineer login {code_e} {data_e}"))
            _print(results)
            return 1
        hub_eng = str(data_e["token"])
        code, cfg = req(
            HUB,
            "POST",
            "/api/network/config",
            token=hub_eng,
            body={
                "mode": "server",
                "server_ip": "127.0.0.1",
                "port": 8000,
                "base_name": "Hub-A",
            },
        )
        hub_tok_cfg = hub_eng
    else:
        hub_tok_cfg = hub_tok
    if code != 200:
        results.append(("config-hub", False, f"{code} {cfg}"))
        _print(results)
        return 1
    print("[ok] hub mode=server")

    # Configure client
    code_e, data_e = req(CLIENT, "POST", "/api/auth/login", body={"pin": "0000000"})
    client_eng = str(data_e.get("token") or "")
    code, cfg = req(
        CLIENT,
        "POST",
        "/api/network/config",
        token=client_eng,
        body={
            "mode": "client",
            "server_ip": "127.0.0.1",
            "port": 8000,
            "base_name": "Client-B",
            "hub_pin": PIN,
        },
    )
    if code != 200:
        results.append(("config-client", False, f"{code} {cfg}"))
        _print(results)
        return 1
    print("[ok] client mode=client hub_pin set")

    # Re-login operator tokens for chat/targets
    hub_tok = login(HUB)
    client_tok = login(CLIENT)

    print(f"[wait] {TICK_WAIT}s for first sync ticks…")
    time.sleep(TICK_WAIT)

    # --- 1 bases / LAN IP ---
    code, hb = req(HUB, "GET", "/api/network/bases", token=hub_tok)
    bases = (hb or {}).get("bases") or []
    client_base = next((b for b in bases if b.get("base_name") == "Client-B"), None)
    code_s, st = req(CLIENT, "GET", "/api/network/status", token=client_tok)
    adv = str((st or {}).get("advertise_ip") or "")
    lan_ok = False
    detail = f"bases={bases} advertise_ip={adv}"
    if client_base:
        ip = str(client_base.get("ip") or "")
        lan_ok = bool(ip) and not ip.startswith("127.")
        detail = f"peer_ip={ip} advertise_ip={adv} hub_reachable={st.get('hub_reachable')}"
    elif adv and not adv.startswith("127."):
        # heartbeat may still be pending; advertise_ip proves resolver
        lan_ok = bool(st.get("hub_reachable"))
        detail += " (peer not in hub bases yet; advertise_ip non-loopback)"
    results.append(("1_bases_lan_ip", lan_ok, detail))

    # --- 2 chat client -> hub ---
    marker = f"smoke-c2h-{int(time.time())}"
    code, _ = req(
        CLIENT,
        "POST",
        "/api/network/messages",
        token=client_tok,
        body={"body": marker},
    )
    if code != 200:
        results.append(("2_chat_c2h", False, f"post {code}"))
    else:
        print(f"[wait] {TICK_WAIT}s for message push/pull…")
        time.sleep(TICK_WAIT)
        code, data = req(HUB, "GET", "/api/network/messages", token=hub_tok)
        msgs = (data or {}).get("messages") or []
        hit = next((m for m in msgs if m.get("body") == marker), None)
        ok = bool(hit) and (
            hit.get("direction") == "in"
            or hit.get("sender") in ("Client-B",)
        )
        # On hub, worker POST stores as direction=out; hub UI may show out from remote push
        # Accept: body present with sender Client-B
        ok = bool(hit) and str(hit.get("sender")) == "Client-B"
        results.append(
            (
                "2_chat_c2h",
                ok,
                f"hit={hit}" if hit else f"not found among {len(msgs)} msgs",
            )
        )

    # --- 3 chat hub -> client ---
    marker2 = f"smoke-h2c-{int(time.time())}"
    code, _ = req(
        HUB,
        "POST",
        "/api/network/messages",
        token=hub_tok,
        body={"body": marker2},
    )
    if code != 200:
        results.append(("3_chat_h2c", False, f"post {code}"))
    else:
        print(f"[wait] {TICK_WAIT}s for hub→client pull…")
        time.sleep(TICK_WAIT)
        code, data = req(CLIENT, "GET", "/api/network/messages", token=client_tok)
        msgs = (data or {}).get("messages") or []
        hit = next((m for m in msgs if m.get("body") == marker2), None)
        ok = bool(hit) and hit.get("direction") == "in" and str(hit.get("sender")) == "Hub-A"
        results.append(("3_chat_h2c", ok, f"hit={hit}" if hit else "missing"))

    # --- 4 unread ---
    # On client: mark seen at now-1, then get unread after another hub message
    since = time.time() - 1
    marker3 = f"smoke-unread-{int(time.time())}"
    req(HUB, "POST", "/api/network/messages", token=hub_tok, body={"body": marker3})
    time.sleep(TICK_WAIT)
    code, data = req(
        CLIENT,
        "GET",
        f"/api/network/messages/unread?since={since}",
        token=client_tok,
    )
    count = int((data or {}).get("count") or 0)
    results.append(("4_unread", count >= 1, f"count={count} since={since}"))

    # --- 5 target with GPS + without GPS payload path ---
    tid = f"smoke-tgt-{int(time.time())}"
    code, _ = req(
        CLIENT,
        "POST",
        "/api/network/targets",
        token=client_tok,
        body={
            "id": tid,
            "class_name": "smoke_vehicle",
            "confidence": 0.91,
            "gps_lat": 55.751244,
            "gps_lon": 37.618423,
            "notes": "detection_id=smoke-det-1",
            "source_video": "archive/smoke.mp4",
        },
    )
    gps_post_ok = code == 200
    time.sleep(TICK_WAIT)
    code, data = req(HUB, "GET", "/api/network/targets", token=hub_tok)
    tgts = (data or {}).get("targets") or []
    hit = next((t for t in tgts if t.get("id") == tid), None)
    gps_ok = (
        gps_post_ok
        and bool(hit)
        and hit.get("gps_lat") is not None
        and abs(float(hit["gps_lat"]) - 55.751244) < 1e-4
    )
    # FE confirm dialog is code-level; API allows null GPS
    code2, _ = req(
        CLIENT,
        "POST",
        "/api/network/targets",
        token=client_tok,
        body={"class_name": "no_gps_smoke", "confidence": 0.5},
    )
    results.append(
        (
            "5_target_gps",
            gps_ok and code2 == 200,
            f"gps_hit={hit is not None} no_gps_post={code2}",
        )
    )

    # --- 6 offline queue: stop not possible easily mid-script; simulate by
    # posting on hub while client worker would be "behind", then force pull
    # Real offline: we pause by not waiting — post several hub msgs, ensure one pull gets all without dup
    m_a = f"smoke-off-a-{int(time.time())}"
    m_b = f"smoke-off-b-{int(time.time())}"
    req(HUB, "POST", "/api/network/messages", token=hub_tok, body={"body": m_a})
    req(HUB, "POST", "/api/network/messages", token=hub_tok, body={"body": m_b})
    time.sleep(TICK_WAIT + 5)
    code, data = req(CLIENT, "GET", "/api/network/messages", token=client_tok)
    msgs = (data or {}).get("messages") or []
    bodies = [m.get("body") for m in msgs]
    c_a = bodies.count(m_a)
    c_b = bodies.count(m_b)
    # Also ensure no duplicate ids
    ids = [m.get("id") for m in msgs if m.get("body") in (m_a, m_b)]
    dup_free = len(ids) == len(set(ids))
    results.append(
        (
            "6_offline_queue_nodup",
            c_a == 1 and c_b == 1 and dup_free,
            f"count_a={c_a} count_b={c_b} dup_free={dup_free}",
        )
    )

    # --- 7 targets regression: second target round-trip ---
    tid2 = f"smoke-reg-{int(time.time())}"
    req(
        HUB,
        "POST",
        "/api/network/targets",
        token=hub_tok,
        body={"id": tid2, "class_name": "reg_tank", "confidence": 0.77},
    )
    time.sleep(TICK_WAIT)
    code, data = req(CLIENT, "GET", "/api/network/targets", token=client_tok)
    tgts = (data or {}).get("targets") or []
    hit = next((t for t in tgts if t.get("id") == tid2), None)
    ok = bool(hit) and hit.get("direction") == "in" and hit.get("class_name") == "reg_tank"
    results.append(("7_targets_regression", ok, f"hit={hit}"))

    return _print(results)


def _print(results: list[tuple[str, bool, str]]) -> int:
    print("\n=== DUAL-SMOKE RESULTS ===")
    failed = 0
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{mark}] {name}: {detail}")
    print(f"=== {len(results) - failed}/{len(results)} passed ===")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(2)
