"""Phase 4 API smoke (train status, models status, system, factory-reset auth)."""
from __future__ import annotations

import os
import sys

import httpx

BASE = os.environ.get("MURAVEI_SMOKE_BASE", "http://127.0.0.1:8001")


def main() -> int:
    fails: list[str] = []
    with httpx.Client(timeout=30.0) as c:
        # engineer login
        eng = c.post(f"{BASE}/api/auth/login", json={"pin": "0000000"})
        if eng.status_code != 200:
            print("ENGINEER login failed", eng.text)
            return 1
        eh = {"Authorization": f"Bearer {eng.json()['token']}"}
        print("LOGIN engineer ok")

        hw = c.get(f"{BASE}/api/system/hardware", headers=eh)
        assert hw.status_code == 200, hw.text
        print("HARDWARE", {k: hw.json().get(k) for k in ("cpu_percent", "ram_total_mb", "gpu")})

        st = c.post(f"{BASE}/api/system/selftest", headers=eh)
        assert st.status_code == 200, st.text
        print("SELFTEST ok=", st.json().get("ok"), "checks=", len(st.json().get("checks") or []))

        for t in ("ollama_offline", "clear"):
            r = c.post(f"{BASE}/api/system/simulate-failure", headers=eh, json={"type": t})
            assert r.status_code == 200, r.text
            print("SIM", t, r.json())

        ms = c.get(f"{BASE}/api/models/status", headers=eh)
        assert ms.status_code == 200, ms.text
        print("MODELS status", ms.json().get("best_exists"), ms.json().get("best_path"))

        # operator train status
        op = c.post(f"{BASE}/api/auth/login", json={"pin": "1234567"})
        oh = {"Authorization": f"Bearer {op.json()['token']}"}
        ts = c.get(f"{BASE}/api/train/status", headers=oh)
        assert ts.status_code == 200, ts.text
        print("TRAIN status", ts.json().get("status"))

        # change operator pin then restore (engineer)
        ch = c.post(
            f"{BASE}/api/auth/change-pin",
            headers=eh,
            json={"role": "operator", "pin": "7654321"},
        )
        assert ch.status_code == 200, ch.text
        peek = c.get(f"{BASE}/api/auth/peek-pin/operator", headers=eh)
        assert peek.status_code == 200 and peek.json().get("pin") == "7654321", peek.text
        print("PEEK/CHANGE ok")
        ch2 = c.post(
            f"{BASE}/api/auth/change-pin",
            headers=eh,
            json={"role": "operator", "pin": "1234567"},
        )
        assert ch2.status_code == 200, ch2.text

        # master factory reset
        master = c.post(f"{BASE}/api/auth/login", json={"pin": "0987907"})
        mh = {"Authorization": f"Bearer {master.json()['token']}"}
        fr = c.post(
            f"{BASE}/api/auth/factory-reset",
            headers=mh,
            json={"current_master_pin": "0987907"},
        )
        assert fr.status_code == 200, fr.text
        print("FACTORY RESET", fr.json())

        # operator cannot access system
        deny = c.get(f"{BASE}/api/system/hardware", headers=oh)
        if deny.status_code not in (401, 403):
            fails.append(f"operator should be denied system, got {deny.status_code}")

    if fails:
        print("FAILS", fails)
        return 1
    print("PHASE4_SMOKE_GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
