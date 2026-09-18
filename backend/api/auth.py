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
)
from services.security import (
    JWT_ALG,
    TOKEN_TTL_SEC,
    get_current_user,
    require_role,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_FAILS = 5
LOCK_SEC = 120

# P1-12: In-memory token store with hash-only storage
# Tokens are stored as SHA-256 hashes to prevent leak from crash dumps
_active_tokens: dict[str, dict[str, Any]] = {}  # hash -> {role, exp, username}


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
    """Generate session token with hash-only storage (P1-12).
    
    Returns (plain_token, token_hash) — only hash is stored.
    Token is a random hex string (not JWT) to prevent forgery.
    """
    plain_token = secrets.token_hex(32)  # 64-char random token
    token_hash = hashlib.sha256(plain_token.encode()).hexdigest()
    exp = time.time() + TOKEN_TTL_SEC
    
    # Store hash -> metadata
    _active_tokens[token_hash] = {
        "role": role,
        "exp": exp,
        "username": username,
    }
    
    return plain_token, token_hash


def _invalidate_token(token: str) -> None:
    """Remove token from active store by hash."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    _active_tokens.pop(token_hash, None)


def _validate_session_token(
    request: Request,
) -> str:
    """Validate token from query param or Authorization header (P1-12)."""
    token = request.query_params.get("token") or (
        request.headers.get("authorization") or ""
    ).replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = _active_tokens.get(token_hash)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    if session["exp"] < time.time():
        _active_tokens.pop(token_hash, None)
        raise HTTPException(status_code=401, detail="Token expired")
    
    return token


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    init_db()
    key = request.client.host if request.client else "local"
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
