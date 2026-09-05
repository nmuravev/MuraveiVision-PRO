"""Smoke Sprint B.2: FullKit stage layout + ollama_proxy retries + muravei_env 3.12.

Does NOT download Ollama or build the full ZIP (too large). Checks:
- host muravei_env is 3.12
- ollama_proxy UNAVAILABLE message + retry constants
- if portable/MuraveiVision_PRO_FullKit exists → layout asserts
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

OUT = ROOT / "logs" / "smoke_fullkit_layout.json"
FULL_STAGE = ROOT / "portable" / "MuraveiVision_PRO_FullKit"
LITE_STAGE = ROOT / "portable" / "MuraveiVision_PRO_Portable"


def main() -> int:
    # Host muravei_env must be 3.12 (this script should be launched via it)
    ver = sys.version
    assert ver.startswith("3.12"), f"expected muravei_env 3.12, got {ver}"

    import importlib

    importlib.import_module("main")
    from services import ollama_proxy as op

    assert op.TAGS_RETRIES >= 3
    assert op.TAGS_RETRY_DELAY_SEC >= 2.0
    assert "ollama/ollama.exe" in op.UNAVAILABLE.lower() or "ollama.exe" in op.UNAVAILABLE

    # list_models: if Ollama down → available False + message; if up → ok
    t0 = time.time()
    res = op.list_models()
    elapsed = time.time() - t0
    assert "available" in res
    if not res.get("available"):
        assert "Ollama" in (res.get("message") or "")
    payload: dict = {
        "ok": True,
        "python": ver.split()[0],
        "tags_retries": op.TAGS_RETRIES,
        "list_models_available": res.get("available"),
        "list_models_message": res.get("message"),
        "list_models_count": len(res.get("models") or []),
        "list_models_elapsed_sec": round(elapsed, 2),
        "full_stage": None,
        "lite_stage_exists": LITE_STAGE.is_dir(),
    }

    if FULL_STAGE.is_dir():
        ollama_exe = FULL_STAGE / "ollama" / "ollama.exe"
        if not ollama_exe.is_file():
            found = list(FULL_STAGE.joinpath("ollama").rglob("ollama.exe")) if (FULL_STAGE / "ollama").is_dir() else []
            assert found, "FullKit stage missing ollama.exe"
            ollama_exe = found[0]
        models = FULL_STAGE / "ollama" / "models"
        assert models.is_dir(), "FullKit missing ollama/models"
        # qwen marker somewhere under models
        qwen_hits = [p for p in models.rglob("*") if "qwen2.5vl" in p.name.lower() or "qwen2.5vl" in str(p).lower()]
        assert qwen_hits, "FullKit models missing qwen2.5vl"
        env_py = FULL_STAGE / "muravei_env" / "Scripts" / "python.exe"
        if not env_py.is_file():
            env_py = FULL_STAGE / "muravei_env" / "python.exe"
        assert env_py.is_file(), "FullKit missing muravei_env python"
        bat = FULL_STAGE / "Запустить.bat"
        assert bat.is_file()
        bat_txt = bat.read_text(encoding="utf-8", errors="replace")
        assert "OLLAMA_MODELS" in bat_txt
        assert "ollama.exe" in bat_txt
        readme = FULL_STAGE / "PORTABLE_README.md"
        colmap = FULL_STAGE / "sidecars" / "colmap"
        gsplat = FULL_STAGE / "sidecars" / "gsplat_examples" / "simple_trainer.py"
        av_bin = (
            FULL_STAGE
            / "sidecars"
            / "alicevision"
            / "windows-x64"
            / "bin"
            / "aliceVision_featureExtraction.exe"
        )
        payload["full_stage"] = {
            "path": str(FULL_STAGE),
            "ollama_exe": str(ollama_exe),
            "qwen_hits": len(qwen_hits),
            "has_readme": readme.is_file(),
            "has_muravei_env": True,
            "has_colmap_sidecar": colmap.is_dir(),
            "has_gsplat_examples": gsplat.is_file(),
            "has_alicevision_sidecar": av_bin.is_file(),
        }
        if colmap.is_dir():
            assert (
                (colmap / "COLMAP.bat").is_file()
                or (colmap / "colmap.exe").is_file()
                or (colmap / "bin" / "colmap.exe").is_file()
            ), "sidecars/colmap present but no COLMAP binary/bat"
        # AliceVision is optional even in FullKit — only assert when present
        if (FULL_STAGE / "sidecars" / "alicevision").is_dir() and not av_bin.is_file():
            raise AssertionError("sidecars/alicevision present but featureExtraction.exe missing")
    else:
        payload["full_stage"] = {
            "path": str(FULL_STAGE),
            "present": False,
            "hint": "Run: npm run portable:full  (requires ollama pull qwen2.5vl:7b)",
        }

    mini = ROOT / "portable" / "MuraveiVision_PRO_Mini"
    payload["mini_stage_exists"] = mini.is_dir()
    if mini.is_dir():
        pts = list((mini / "assets" / "models").glob("*.pt")) if (mini / "assets" / "models").is_dir() else []
        payload["mini_pt_count"] = len(pts)
        assert len(pts) == 0, f"Mini kit must not ship detect .pt, found {[p.name for p in pts]}"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[SMOKE] OK {json.dumps(payload, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
