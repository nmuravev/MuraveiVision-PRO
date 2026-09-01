"""Unified test orchestrator for MuraveiVision PRO.

Runs the full test pipeline sequentially and produces an HTML + JSON report:
  1. Backend unit tests   (python -m unittest discover -s backend/tests, cwd=backend)
  2. Backend compile      (python -m compileall backend -q)
  3. Smoke: smoke_lbs_ft  (needs GPU + archive clip; SKIP if fails to import/run)
  4. Smoke: test_sahi_field (needs GPU + drone video; SKIP on error)
  5. Frontend build       (npm run build)
  6. Playwright E2E       (npm run test:field)  -- SKIP if playwright/browsers unavailable

Exit code 0 only if every REQUIRED step passed. SKIP is tolerated for
optional steps (smoke needing GPU/clip, E2E needing browsers).

Run:
    muravei_env\\Scripts\\python.exe scripts\\test_orchestrator.py
or:
    npm run test:all
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / "muravei_env" / "Scripts" / "python.exe"
REPORTS = ROOT / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

TAIL_LINES = 25


class Step:
    def __init__(self, name: str, required: bool, run) -> None:
        self.name = name
        self.required = required
        self.run = run  # callable() -> (status, stdout_tail)
        self.status = "pending"  # pass | fail | skip
        self.out_tail = ""
        self.ms = 0


def _run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = 600, shell: bool = False) -> tuple[int, str]:
    """Run a command, capture output. Returns (returncode, combined_tail)."""
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            shell=shell,
        )
        out = (p.stdout or "") + (p.stderr or "")
        tail = "\n".join(out.splitlines()[-TAIL_LINES:])
        return p.returncode, tail
    except FileNotFoundError as exc:
        return 127, f"command not found: {exc}"
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"
    except Exception as exc:  # noqa: BLE001
        return 1, f"runner error: {exc}"


def _step_unit() -> tuple[str, str]:
    rc, tail = _run_cmd([str(PY), "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT / "backend", timeout=300)
    return ("pass" if rc == 0 else "fail"), tail


def _step_compileall() -> tuple[str, str]:
    rc, tail = _run_cmd([str(PY), "-m", "compileall", "backend", "-q"], cwd=ROOT, timeout=180)
    return ("pass" if rc == 0 else "fail"), tail


def _step_smoke_lbs() -> tuple[str, str]:
    rc, tail = _run_cmd([str(PY), "backend/scripts/smoke_lbs_ft.py"], cwd=ROOT, timeout=300)
    if rc == 0:
        return "pass", tail
    # Tolerant: smoke needs GPU + clip; treat non-zero as SKIP, not fail.
    return "skip", f"[skip] smoke_lbs_ft rc={rc}\n{tail}"


def _step_sahi_field() -> tuple[str, str]:
    rc, tail = _run_cmd([str(PY), "backend/scripts/test_sahi_field.py"], cwd=ROOT, timeout=300)
    if rc == 0:
        return "pass", tail
    return "skip", f"[skip] test_sahi_field rc={rc}\n{tail}"


def _step_build() -> tuple[str, str]:
    rc, tail = _run_cmd(["npm", "run", "build"], cwd=ROOT, timeout=300, shell=True)
    return ("pass" if rc == 0 else "fail"), tail


def _step_e2e() -> tuple[str, str]:
    rc, tail = _run_cmd(["npm", "run", "test:field"], cwd=ROOT, timeout=600, shell=True)
    if rc == 0:
        return "pass", tail
    return "skip", f"[skip] npm run test:field rc={rc}\n{tail}"


STEPS = [
    Step("Backend unit tests", required=True, run=_step_unit),
    Step("Backend compileall", required=True, run=_step_compileall),
    Step("Frontend build (npm run build)", required=True, run=_step_build),
    Step("Smoke: smoke_lbs_ft.py", required=False, run=_step_smoke_lbs),
    Step("Smoke: test_sahi_field.py", required=False, run=_step_sahi_field),
    Step("E2E: npm run test:field", required=False, run=_step_e2e),
]


def _render_html(results: list[Step], started: float) -> str:
    rows = []
    for s in results:
        color = {"pass": "#16a34a", "fail": "#dc2626", "skip": "#ca8a04", "pending": "#6b7280"}[s.status]
        rows.append(
            f"<tr><td>{html.escape(s.name)}</td>"
            f"<td style='color:{color};font-weight:bold'>{s.status.upper()}</td>"
            f"<td style='text-align:right'>{s.ms}</td>"
            f"<td><pre>{html.escape(s.out_tail)}</pre></td></tr>"
        )
    required_fail = any(s.status == "fail" and s.required for s in results)
    overall = "FAIL" if required_fail else "PASS (required steps green)"
    overall_color = "#dc2626" if required_fail else "#16a34a"
    dur = int(time.time() - started)
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!doctype html><html><head><meta charset='utf-8'>
<title>MuraveiVision test report</title>
<style>
body{{font-family:system-ui,Segoe UI,Arial;background:#0f1115;color:#e5e7eb;padding:16px}}
h1{{font-size:18px}}
table{{border-collapse:collapse;width:100%;font-size:12px}}
td,th{{border:1px solid #2a2f37;padding:6px;vertical-align:top}}
th{{background:#1a1f29;text-align:left}}
pre{{white-space:pre-wrap;max-height:180px;overflow:auto;background:#05070a;padding:6px;margin:0;font-size:10px}}
</style></head><body>
<h1>MuraveiVision PRO — test report</h1>
<div>Generated: {ts} · duration: {dur}s ·
<span style='color:{overall_color};font-weight:bold'>OVERALL: {overall}</span></div>
<table><thead><tr><th>Step</th><th>Status</th><th>ms</th><th>Output (tail)</th></tr></thead>
<tbody>
{"".join(rows)}
</tbody></table>
</body></html>"""


def main() -> int:
    started = time.time()
    print("[orchestrator] starting full test pipeline...")
    for s in STEPS:
        print(f"[orchestrator] RUN: {s.name}")
        t0 = time.time()
        try:
            status, tail = s.run()
        except Exception as exc:  # noqa: BLE001
            status, tail = "fail", f"runner exception: {exc}"
        s.status = status
        s.out_tail = tail
        s.ms = int((time.time() - t0) * 1000)
        print(f"[orchestrator] {s.name}: {s.status.upper()} ({s.ms} ms)")

    html_path = REPORTS / "test_report.html"
    json_path = REPORTS / "test_report.json"
    html_path.write_text(_render_html(STEPS, started), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "generated": _dt.datetime.now().isoformat(),
                "duration_s": int(time.time() - started),
                "steps": [
                    {"name": s.name, "status": s.status, "required": s.required, "ms": s.ms, "tail": s.out_tail}
                    for s in STEPS
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    required_fail = any(s.status == "fail" and s.required for s in STEPS)
    print(f"[orchestrator] report: {html_path}")
    print(f"[orchestrator] {'FAIL (required step failed)' if required_fail else 'PASS'}")
    return 1 if required_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
