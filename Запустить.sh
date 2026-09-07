#!/usr/bin/env bash
# Portable / WSL launcher — same module-mode entry as Запустить.bat (Z1 one path).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export MURAVEI_LOG_DIR="${MURAVEI_LOG_DIR:-$ROOT/logs}"
mkdir -p "$MURAVEI_LOG_DIR"

VER="unknown"
if [[ -f "$ROOT/VERSION" ]]; then
  VER="$(tr -d '\r' < "$ROOT/VERSION" | head -n1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ -z "$VER" ]] && VER="unknown"
fi

echo "============================================"
echo "  MuraveiVision PRO v${VER}"
echo "  Starting..."
echo "============================================"

export MURAVEI_BOOTSTRAP_YES="${MURAVEI_BOOTSTRAP_YES:-1}"
if [[ -f "$ROOT/scripts/bootstrap_portable.ps1" ]] && command -v powershell >/dev/null 2>&1; then
  powershell -NoProfile -ExecutionPolicy Bypass -File "$ROOT/scripts/bootstrap_portable.ps1" \
    >>"$MURAVEI_LOG_DIR/bootstrap.log" 2>&1 || {
    echo "[ОШИБКА] bootstrap_portable failed. See logs/bootstrap.log" >&2
    exit 1
  }
fi

PYTHON=""
for c in "$ROOT/muravei_env/Scripts/python.exe" "$ROOT/muravei_env/bin/python" "$ROOT/muravei_env/python.exe"; do
  if [[ -x "$c" || -f "$c" ]]; then PYTHON="$c"; break; fi
done
if [[ -z "$PYTHON" ]]; then
  echo "[ОШИБКА] Python не найден (ожидается muravei_env)." >&2
  exit 1
fi

export MURAVEI_SESSION_TRACE=1
if [[ -f "$ROOT/sidecars/colmap/COLMAP.bat" || -f "$ROOT/sidecars/colmap/colmap.exe" ]]; then
  export COLMAP_ROOT="$ROOT/sidecars/colmap"
fi
if [[ -f "$ROOT/sidecars/alicevision/windows-x64/bin/aliceVision_featureExtraction.exe" ]]; then
  export ALICEVISION_ROOT="$ROOT/sidecars/alicevision/windows-x64"
fi

echo "Starting backend on http://127.0.0.1:8000 ..."
nohup "$PYTHON" -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 \
  >>"$MURAVEI_LOG_DIR/uvicorn.log" 2>&1 &

for i in $(seq 1 60); do
  if "$PYTHON" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)" 2>/dev/null; then
    echo "Backend ready."
    exit 0
  fi
  sleep 2
done
echo "[ERROR] Backend failed to start. Check logs/uvicorn.log" >&2
exit 1
