#!/usr/bin/env bash
# AliceVision offline fetch (POSIX) — reads scripts/alicevision_manifest.json.
# macOS arm64 placeholder: Windows asset only in current manifest; exits with message.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$ROOT/scripts/alicevision_manifest.json"
if [[ ! -f "$MANIFEST" ]]; then
  echo "Missing $MANIFEST" >&2
  exit 1
fi

python3 - <<'PY' "$MANIFEST" "$ROOT"
import hashlib, json, sys, urllib.request, zipfile
from pathlib import Path

man_path, root = Path(sys.argv[1]), Path(sys.argv[2])
man = json.loads(man_path.read_text(encoding="utf-8"))
chosen = man.get("chosen") or {}
url, sha = chosen.get("url"), (chosen.get("sha256") or "").lower()
if not url or not sha:
    sys.exit("manifest.chosen.url / sha256 required")

dl = root / "sidecars" / "alicevision" / "downloads"
out = root / "sidecars" / "alicevision" / "windows-x64"
dl.mkdir(parents=True, exist_ok=True)
zip_path = dl / Path(url).name
if not zip_path.is_file():
    print(f"Downloading {url} ...")
    urllib.request.urlretrieve(url, zip_path)
digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
if digest != sha:
    sys.exit(f"SHA256 mismatch: got {digest} expected {sha}")
print(f"SHA256 OK: {digest}")

stage = dl / "_extract_stage"
if stage.exists():
    import shutil
    shutil.rmtree(stage)
stage.mkdir(parents=True)
with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(stage)

candidates = [p for p in stage.rglob("bin") if p.is_dir() and any(p.glob("aliceVision_*"))]
if not candidates:
    sys.exit(f"No aliceVision bin/ under {stage}")
src = candidates[0].parent
import shutil
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)
for name in ("bin", "lib", "share"):
    s = src / name
    if s.is_dir():
        shutil.copytree(s, out / name)
print(f"Staged AliceVision {chosen.get('version')} → {out}")
print("Note: current official ZIP is Windows-x64; macOS arm64 is a future port.")
PY
