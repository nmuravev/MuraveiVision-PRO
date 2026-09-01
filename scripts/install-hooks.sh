#!/usr/bin/env bash
# Idempotently install the pre-commit hook into .git/hooks/.
# Safe to re-run. Run from the repo root: bash scripts/install-hooks.sh
set -e
cd "$(git rev-parse --show-toplevel)"

SRC="scripts/pre-commit"
DEST=".git/hooks/pre-commit"

if [ ! -f "$SRC" ]; then
  echo "[install-hooks] source hook not found: $SRC" >&2
  exit 1
fi
if [ ! -d ".git/hooks" ]; then
  echo "[install-hooks] .git/hooks missing — is this a git repo?" >&2
  exit 1
fi

cp "$SRC" "$DEST"
chmod +x "$DEST"
echo "[install-hooks] installed $DEST"
