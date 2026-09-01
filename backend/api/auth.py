"""PIN login (7 digits), SHA-256 + base64 storage, JWT sessions."""
from __future__ import annotations

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
    pin_from_b64,
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
PEEK_ROLES = {
    "engineer": ("operator",),
    "master": ("operator", "engineer", "master"),
}


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


def _make_token(role: str) -> str:
    payload = {
        "sub": role,
        "role": role,
        "exp": int(time.time()) + TOKEN_TTL_SEC,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALG)


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
    token = _make_token(role)
    return LoginResponse(token=token, role=role, username=role)


@router.get("/me")
async def me(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"username": user["sub"], "role": user["role"]}


@router.get("/peek-pin/{role}")
async def peek_pin(
    role: str,
    user: dict[str, Any] = Depends(require_role("engineer")),
) -> dict[str, Any]:
    """Return plaintext PIN (from base64). UI must hide it after 4 seconds."""
    allowed = PEEK_ROLES.get(str(user["role"]), ())
    if role not in allowed:
        raise HTTPException(status_code=403, detail="Cannot view this PIN")
    row = get_pin_row(role)
    if not row:
        raise HTTPException(status_code=404, detail="Unknown role")
    return {
        "role": role,
        "pin": pin_from_b64(str(row["pin_b64"])),
        "display_ms": 4000,
    }


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
