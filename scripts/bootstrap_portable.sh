#!/usr/bin/env bash
# Portable bootstrap for Linux/WSL2 (Windows+Linux only; macOS unsupported).
# Z1/Z2/Z3: see scripts/bootstrap_portable.ps1
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/backend"
export MURAVEI_BOOTSTRAP_YES="${MURAVEI_BOOTSTRAP_YES:-0}"
PROFILE="${MURAVEI_BUILD_PROFILE:-${1:-}}"
if [[ -n "$PROFILE" ]]; then
  export MURAVEI_BUILD_PROFILE="$PROFILE"
fi

PY=""
if [[ -x "$ROOT/muravei_env/bin/python" ]]; then
  PY="$ROOT/muravei_env/bin/python"
elif command -v python3.12 >/dev/null 2>&1; then
  PY="$(command -v python3.12)"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
fi
if [[ -z "$PY" ]]; then
  echo "[ОШИБКА] Нужен Python 3.12 (muravei_env или python3.12)." >&2
  exit 1
fi

STAMP="$ROOT/config/local/bootstrap_complete.json"
if [[ -f "$STAMP" ]]; then
  if "$PY" -c "from services.portable_bootstrap import stamp_matches; raise SystemExit(0 if stamp_matches() else 1)"; then
    echo "[INFO] bootstrap_complete.json актуален — пропуск."
    exit 0
  fi
fi

STATUS="$("$PY" -c "from services.portable_bootstrap import audit_env, resolve_build_profile; import json; print(json.dumps(audit_env(resolve_build_profile())))")"
ENV_STATUS="$(printf '%s' "$STATUS" | "$PY" -c "import sys,json; print(json.load(sys.stdin).get('env_status',''))")"
echo "[INFO] Env status: $ENV_STATUS"

if [[ "$ENV_STATUS" == "broken" ]]; then
  echo "[ПРЕДУПРЕЖДЕНИЕ] Битый muravei_env — пересборка."
  rm -rf "$ROOT/muravei_env"
  ENV_STATUS="absent"
fi

if [[ "$ENV_STATUS" == "absent" ]]; then
  if [[ ! -f "$ROOT/scripts/setup_env.ps1" ]]; then
    echo "[ОШИБКА] На Linux создайте venv вручную: python3.12 -m venv muravei_env && pip install -r backend/requirements.txt" >&2
    # Minimal POSIX setup
    python3.12 -m venv "$ROOT/muravei_env"
    PY="$ROOT/muravei_env/bin/python"
    WHEELS="$ROOT/wheels"
    if [[ -n "${MURAVEI_WHEELS_DIR:-}" ]]; then WHEELS="$MURAVEI_WHEELS_DIR"; fi
    if ls "$WHEELS"/*.whl >/dev/null 2>&1; then
      "$PY" -m pip install --upgrade pip
      "$PY" -m pip install --no-index --find-links="$WHEELS" -r "$ROOT/backend/requirements.txt"
    else
      if [[ "${MURAVEI_BOOTSTRAP_ONLINE:-1}" == "0" ]]; then
        echo "[ОШИБКА] Нет wheels/ и сеть запрещена." >&2
        exit 1
      fi
      "$PY" -m pip install --upgrade pip
      "$PY" -m pip install --no-cache-dir -r "$ROOT/backend/requirements.txt"
    fi
  else
    echo "[INFO] Предпочтительно bootstrap_portable.ps1 на Windows; WSL: создаём venv…"
    python3.12 -m venv "$ROOT/muravei_env"
    PY="$ROOT/muravei_env/bin/python"
    WHEELS="${MURAVEI_WHEELS_DIR:-$ROOT/wheels}"
    if ls "$WHEELS"/*.whl >/dev/null 2>&1; then
      "$PY" -m pip install --upgrade pip
      "$PY" -m pip install --no-index --find-links="$WHEELS" -r "$ROOT/backend/requirements.txt"
    else
      "$PY" -m pip install --upgrade pip
      "$PY" -m pip install --no-cache-dir -r "$ROOT/backend/requirements.txt"
    fi
  fi
  PY="$ROOT/muravei_env/bin/python"
fi

"$PY" -c "from services.portable_bootstrap import heal_env; import json,sys; r=heal_env(); print(json.dumps(r,ensure_ascii=False)); sys.exit(0 if r.get('ok') else 1)"

"$PY" - <<'PY'
from services.hardware_detect import detect_all, classify_tier
from services.portable_bootstrap import apply_hardware_profile, resolve_build_profile, write_stamp
from services.hardware_detect import detect_colmap, detect_alicevision
snap = detect_all()
tier = snap.get("tier") or classify_tier()
bp = resolve_build_profile()
apply_hardware_profile(bp, tier)
print(snap.get("badge_ru") or "")
mm = snap.get("mismatch")
if mm:
    print(f"[{mm.get('level')}] {mm.get('message_ru')}")
write_stamp(
    build_profile=bp,
    messages=["bootstrap_portable.sh"],
    component_versions={
        "colmap": detect_colmap().get("present"),
        "alicevision": detect_alicevision().get("present"),
    },
)
print("Bootstrap OK")
PY
