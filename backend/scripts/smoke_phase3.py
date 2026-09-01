"""Phase 3 smoke acceptance against running backend."""
from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from pathlib import Path

import httpx

import os

BASE = os.environ.get("MURAVEI_SMOKE_BASE", "http://127.0.0.1:8000")
ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "archive"


def main() -> int:
    fails: list[str] = []
    with httpx.Client(timeout=60.0) as client:
        h = client.get(f"{BASE}/api/health")
        assert h.status_code == 200, h.text
        print("HEALTH ok")

        login = client.post(f"{BASE}/api/auth/login", json={"pin": "1234567"})
        assert login.status_code == 200, login.text
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("LOGIN ok", login.json().get("role"))

        models = client.get(f"{BASE}/api/ai/models", headers=headers)
        assert models.status_code == 200, models.text
        m = models.json()
        print("AI_MODELS", m.get("available"), "count", len(m.get("models") or []), m.get("message", "")[:60])
        if m.get("available") is False:
            assert "ИИ недоступен" in (m.get("message") or ""), "expected honest unavailable message"

        preferred = None
        for item in m.get("models") or []:
            name = str(item.get("name") or "")
            low = name.lower()
            if item.get("embed"):
                continue
            if "coder" in low:
                continue
            preferred = name
            # prefer small non-vl for smoke speed
            if "vl" not in low and "vision" not in low and "llava" not in low:
                break
        if not preferred and m.get("models"):
            preferred = m["models"][0]["name"]

        analyze = client.post(
            f"{BASE}/api/ai/analyze",
            headers=headers,
            json={"prompt": "Ответь одним словом: ок", "model": preferred},
            timeout=90.0,
        )
        if not m.get("available"):
            if analyze.status_code != 503:
                fails.append(f"analyze expected 503 when Ollama off, got {analyze.status_code}")
            detail = ""
            try:
                detail = str(analyze.json().get("detail") or analyze.text)
            except Exception:
                detail = analyze.text
            if "ИИ недоступен" not in detail and "stub" in detail.lower():
                fails.append("analyze returned stub text")
            print("AI_ANALYZE unavailable ->", analyze.status_code, detail[:80])
        else:
            assert analyze.status_code == 200, analyze.text
            text = (analyze.json().get("analysis") or "").strip()
            assert text, "empty analysis with Ollama available"
            print("AI_ANALYZE ok chars", len(text))

        rep = client.get(f"{BASE}/api/report/html", headers=headers)
        assert rep.status_code == 200, rep.text
        html = rep.text
        for needle in ("dashboard", "search-input", "@media print", "detection-grid", "class-filter"):
            if needle not in html:
                fails.append(f"report missing {needle}")
        if "cdn." in html or "googleapis" in html:
            fails.append("report loads external CDN")
        print("REPORT ok bytes", len(html))

        dz = client.post(f"{BASE}/api/export/dataset-zip", headers=headers)
        assert dz.status_code == 200, dz.text
        with zipfile.ZipFile(io.BytesIO(dz.content)) as zf:
            names = zf.namelist()
            assert "dataset.yaml" in names, names[:20]
            blob = "\n".join(zf.read(n).decode("utf-8", "replace") for n in names if n.endswith((".txt", ".yaml", ".json")))
            if "1234567" in blob or "0987907" in blob or "pin_b64" in blob:
                fails.append("dataset zip may contain PIN material")
        print("DATASET_ZIP ok bytes", len(dz.content), "entries", len(names))

        sz = client.post(f"{BASE}/api/support/diagnostic-zip", headers=headers)
        assert sz.status_code == 200, sz.text
        with zipfile.ZipFile(io.BytesIO(sz.content)) as zf:
            names = zf.namelist()
            assert any(n.startswith("logs/") or n == "hardware_specs.json" for n in names), names
            blob = "\n".join(
                zf.read(n).decode("utf-8", "replace")
                for n in names
                if n.endswith((".txt", ".json")) and zf.getinfo(n).file_size < 2_000_000
            )
            # hardware JSON must not include PIN fields
            if '"pin"' in blob.lower() and "1234567" in blob:
                fails.append("diagnostic zip may contain PIN")
        print("DIAG_ZIP ok bytes", len(sz.content))

        rl = client.get(f"{BASE}/api/rec/list", headers=headers)
        assert rl.status_code == 200, rl.text
        print("REC_LIST ok", rl.json().get("root"), "files", len(rl.json().get("files") or []))

        # REC with real sample if present
        samples = list((ARCHIVE / "captures").rglob("*.mp4")) if (ARCHIVE / "captures").exists() else []
        if not samples:
            # create a tiny valid-ish path under archive for path check (may fail open)
            demo_dir = ARCHIVE / "captures" / "drones"
            demo_dir.mkdir(parents=True, exist_ok=True)
            print("REC_START skipped (no mp4 samples)")
        else:
            demo = samples[0]
            start = client.post(
                f"{BASE}/api/rec/start",
                headers=headers,
                json={"drone_id": "viewer-1", "source_path": str(demo), "start_sec": 0},
            )
            if start.status_code != 200:
                fails.append(f"rec start failed: {start.status_code} {start.text[:200]}")
                print("REC_START fail", start.status_code, start.text[:200])
            else:
                print("REC_START", start.json())
                time.sleep(2)
                stop = client.post(
                    f"{BASE}/api/rec/stop",
                    headers=headers,
                    json={"drone_id": "viewer-1"},
                )
                assert stop.status_code == 200, stop.text
                print("REC_STOP", stop.json())
                path = stop.json().get("path")
                if not path or not Path(path).is_file():
                    fails.append("rec stop did not produce file")
                else:
                    print("REC_FILE", path, "bytes", Path(path).stat().st_size)

    if fails:
        print("FAILS:")
        for f in fails:
            print(" -", f)
        return 1
    print("SMOKE_ALL_GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
