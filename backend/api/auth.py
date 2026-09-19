"""PIN login (7 digits), SHA-256 + base64 storage, JWT sessions."""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from services.db import (
    clear_lockout,
    find_role_by_pin,
    get_jwt_secret,
    get_lockout,
    get_pin_row,
    init_db,
    record_failed_login,
    update_pin,
    add_session_token,
    get_session_token,
    remove_session_token,
    cleanup_expired_sessions,
)
from services.security import (
    JWT_ALG,
    TOKEN_TTL_SEC,
    client_key,
    get_current_user,
    require_role,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_FAILS = 5
LOCK_SEC = 120

# P1-12: Hybrid token store (DB-backed + in-memory cache)
# Tokens persisted to DB survive restarts; in-memory cache for fast lookups
_active_tokens: dict[str, dict[str, Any]] = {}  # hash -> {role, exp, username}
_last_db_sync: float = 0  # timestamp of last DB sync
_DB_SYNC_INTERVAL = 300  # sync in-memory cache every 5 minutes


def _sync_db_to_memory() -> None:
    """Load active sessions from DB to in-memory cache (P6.1)."""
    global _last_db_sync
    now = time.time()
    if now - _last_db_sync < _DB_SYNC_INTERVAL and _active_tokens:
        return  # Skip if cache is fresh
    
    _active_tokens.clear()
    try:
        from services.db import _connect
        conn = _connect()
        try:
            cutoff = now - (24 * 3600)  # Load last 24h
            rows = conn.execute(
                "SELECT token_hash, role, username, exp FROM session_tokens WHERE exp > ? AND created_at > ?",
                (now, cutoff),
            ).fetchall()
            for row in rows:
                _active_tokens[row["token_hash"]] = {
                    "role": row["role"],
                    "exp": row["exp"],
                    "username": row["username"],
                    "created_at": now,
                }
            _last_db_sync = now
        finally:
            conn.close()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(f"[session] DB sync failed: {exc}")


def _sync_memory_to_db() -> None:
    """Persist in-memory tokens to DB (P6.1)."""
    global _last_db_sync
    now = time.time()
    if now - _last_db_sync < _DB_SYNC_INTERVAL:
        return  # Skip if already synced recently
    
    for token_hash, session in _active_tokens.items():
        if session.get("exp", 0) > now:
            add_session_token(
                token_hash,
                session["role"],
                session["username"],
                session["exp"],
            )
    _last_db_sync = now


def cleanup_expired_tokens(max_age_hours: int = 24) -> int:
    """Remove expired tokens from active store. Returns count of removed."""
    now = time.time()
    expired = [
        h for h, t in _active_tokens.items()
        if now - t.get("created_at", 0) > max_age_hours * 3600 or t.get("exp", 0) < now
    ]
    for h in expired:
        del _active_tokens[h]
        remove_session_token(h)  # Also remove from DB
    return len(expired)


class LoginRequest(BaseModel):
    pin: str = Field(..., min_length=7, max_length=7, pattern=r"^\d{7}$")


class LoginResponse(BaseModel):
    token: str
    role: str
    username: str


class ChangePinRequest(BaseModel):
    role: str
    pin: str = Field(..., min_length=7, max_length=7, pattern=r"^\d{7}$")
    current_master_pin: str | None = None


def _make_token(role: str, username: str) -> tuple[str, str]:
    """Generate session token with hash-only storage (P1-12, P6.1 DB-backed).
    
    Returns (plain_token, token_hash) — only hash is stored.
    Token is a random hex string (not JWT) to prevent forgery.
    Persists to DB for survival across restarts.
    """
    plain_token = secrets.token_hex(32)  # 64-char random token
    token_hash = hashlib.sha256(plain_token.encode()).hexdigest()
    exp = time.time() + TOKEN_TTL_SEC
    
    # Store in in-memory cache
    _active_tokens[token_hash] = {
        "role": role,
        "exp": exp,
        "username": username,
        "created_at": time.time(),
    }
    
    # Persist to DB (P6.1)
    try:
        add_session_token(token_hash, role, username, exp)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(f"[session] DB persist failed: {exc}")
    
    return plain_token, token_hash


def _invalidate_token(token: str) -> None:
    """Remove token from active store by hash (P6.1: also from DB)."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    _active_tokens.pop(token_hash, None)
    try:
        remove_session_token(token_hash)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(f"[session] DB invalidate failed: {exc}")


def _validate_session_token(
    request: Request,
) -> str:
    """Validate token from query param or Authorization header (P1-12, P6.1 DB-backed)."""
    token = request.query_params.get("token") or (
        request.headers.get("authorization") or ""
    ).replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    # Check in-memory cache first
    session = _active_tokens.get(token_hash)
    
    # Fallback to DB (P6.1)
    if session is None:
        try:
            db_session = get_session_token(token_hash)
            if db_session:
                # Restore to in-memory cache
                _active_tokens[token_hash] = db_session
                session = db_session
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(f"[session] DB lookup failed: {exc}")
    
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    if session["exp"] < time.time():
        _active_tokens.pop(token_hash, None)
        try:
            remove_session_token(token_hash)
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="Token expired")
    
    return token


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    init_db()
    # P2-3: Use client_key() for NAT/Proxy support (X-Forwarded-For)
    key = client_key(request)
    state = get_lockout(key)
    now = time.time()
    if state["locked_until"] > now:
        remaining = int(state["locked_until"] - now)
        raise HTTPException(
            status_code=429,
            detail=f"Too many attempts. Try again in {remaining}s",
        )

    role = find_role_by_pin(body.pin)
    if not role:
        record_failed_login(key, max_fails=MAX_FAILS, lock_sec=LOCK_SEC)
        raise HTTPException(status_code=401, detail="Invalid PIN")

    clear_lockout(key)
    token, _ = _make_token(role, role)
    return LoginResponse(token=token, role=role, username=role)


@router.get("/me")
async def me(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"username": user["sub"], "role": user["role"]}


@router.post("/logout")
async def logout(
    token: str = Depends(_validate_session_token),
) -> dict[str, Any]:
    """Invalidate current session token (P1-12)."""
    _invalidate_token(token)
    return {"ok": True, "message": "Session invalidated"}


# P1-1: /peek-pin REMOVED — plaintext PIN exposure risk
# Use CLI script scripts/reset_pin.py for admin PIN management


@router.post("/change-pin")
async def change_pin(
    body: ChangePinRequest,
    user: dict[str, Any] = Depends(require_role("engineer")),
) -> dict[str, Any]:
    actor = str(user["role"])
    if body.role == "operator" and actor not in ("engineer", "master"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if body.role in ("engineer", "master") and actor != "master":
        raise HTTPException(status_code=403, detail="Forbidden")
    if body.role == "master":
        if not body.current_master_pin or find_role_by_pin(body.current_master_pin) != "master":
            raise HTTPException(status_code=401, detail="Current master PIN required")
    if get_pin_row(body.role) is None:
        raise HTTPException(status_code=404, detail="Unknown role")
    update_pin(body.role, body.pin)
    return {"ok": True, "role": body.role}


class FactoryResetBody(BaseModel):
    current_master_pin: str = Field(..., min_length=7, max_length=7, pattern=r"^\d{7}$")


@router.post("/factory-reset")
async def factory_reset(
    body: FactoryResetBody,
    user: dict[str, Any] = Depends(require_role("master")),
) -> dict[str, Any]:
    if find_role_by_pin(body.current_master_pin) != "master":
        raise HTTPException(status_code=401, detail="Current master PIN required")
    from services.db import DEFAULT_PINS

    for role, pin in DEFAULT_PINS.items():
        update_pin(role, pin)
    return {"ok": True, "pins_restored": list(DEFAULT_PINS.keys())}
