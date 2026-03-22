"""JWT and password security utilities."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

import bcrypt as _bcrypt
import structlog
from fastapi import HTTPException, Request
from jose import JWTError, jwt

from core.config import settings

log = structlog.get_logger(__name__)

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24


def _get_jwt_secret() -> str:
    """Return JWT secret, sha256-hashed if shorter than 32 chars."""
    raw = settings.hitl_jwt_secret
    if len(raw) < 32:
        return hashlib.sha256(raw.encode()).hexdigest()
    return raw


@dataclass
class TokenData:
    """Decoded JWT payload."""

    user_id: UUID
    email: str
    role: str
    teams: list[str] = field(default_factory=list)
    culture: str = "fr"


def encode_token(
    user_id: str,
    email: str,
    role: str,
    teams: list[str],
    culture: str = "fr",
) -> str:
    """Create a signed JWT token."""
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "teams": teams,
        "culture": culture,
        "exp": expire,
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT token. Raises on invalid/expired."""
    return jwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Truncates to 72 bytes (bcrypt limit)."""
    truncated = password.encode("utf-8")[:72]
    salt = _bcrypt.gensalt()
    return _bcrypt.hashpw(truncated, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    truncated = plain.encode("utf-8")[:72]
    try:
        return _bcrypt.checkpw(truncated, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


async def get_current_user(request: Request) -> TokenData:
    """FastAPI dependency — extract and validate JWT from Authorization header."""
    auth_header: Optional[str] = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="auth.missing_token")

    token = auth_header[7:]
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="auth.invalid_token")

    try:
        return TokenData(
            user_id=UUID(payload["sub"]),
            email=payload.get("email", ""),
            role=payload.get("role", "member"),
            teams=payload.get("teams", []),
            culture=payload.get("culture", "fr"),
        )
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="auth.invalid_token")
