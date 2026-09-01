"""Path confinement and JWT role guards."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import jwt
from fastapi import Depends, HTTPException, Query, Request, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

BASE_DIR = Path(__file__).resolve().parents[2]


def safe_path_resolve(path: str | Path) -> Path:
    try:
        return Path(path).resolve()
    except (FileNotFoundError, OSError, NotADirectoryError):
        return Path(path).absolute()


from services.db import get_jwt_secret, init_db

JWT_ALG = "HS256"
TOKEN_TTL_SEC = 60 * 60 * 8

ROLE_LEVEL = {
    "operator": 1,
    "engineer": 2,
    "master": 3,
}

security = HTTPBearer(auto_error=False)


def archive_root() -> Path:
    return (BASE_DIR / "archive").resolve()


def assert_in_archive(path: str | Path) -> Path:
    """Resolve path and reject anything outside archive/. Raises HTTP 403."""
    init_db()
    target = safe_path_resolve(path)
    root = archive_root()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Path outside archive") from exc
    return target


def decode_token(token: str) -> dict[str, Any]:
    if not token or token.startswith("dev-token:"):
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    role = str(payload.get("role", ""))
    if role not in ROLE_LEVEL:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


def _token_from_request(
    creds: HTTPAuthorizationCredentials | None,
    token_q: str | None,
) -> str:
    if creds and creds.credentials:
        return creds.credentials
    if token_q:
        return token_q
    raise HTTPException(status_code=401, detail="Unauthorized")


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    token: str | None = Query(default=None),
) -> dict[str, Any]:
    return decode_token(_token_from_request(creds, token))


def require_role(*allowed: str) -> Callable[..., dict[str, Any]]:
    """Allow the named roles and any higher role (operator < engineer < master)."""
    if not allowed:
        allowed = ("operator",)
    min_level = min(ROLE_LEVEL[r] for r in allowed if r in ROLE_LEVEL)

    def _dep(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        role = str(user.get("role", ""))
        if ROLE_LEVEL.get(role, 0) < min_level:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user

    return _dep


async def ws_user(websocket: WebSocket) -> dict[str, Any]:
    """Read JWT from WebSocket query ?token=... (browsers cannot set WS headers)."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        raise HTTPException(status_code=401, detail="Unauthorized")
    return decode_token(token)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "local"
