"""Authentication service — login, register, Google OAuth, password reset."""

from __future__ import annotations

import secrets
import string
from typing import Any
from uuid import UUID

import httpx
import structlog

from core.config import load_json_config, settings
from core.database import execute, fetch_all, fetch_one
from core.security import encode_token, hash_password, verify_password
from schemas.auth import TokenResponse, UserResponse
from schemas.common import SuccessResponse
from services.email_service import send_reset_email

log = structlog.get_logger(__name__)


def _generate_temp_password(length: int = 12) -> str:
    """Generate a temporary password with upper, lower, digit, special."""
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        has_upper = any(c.isupper() for c in pw)
        has_lower = any(c.islower() for c in pw)
        has_digit = any(c.isdigit() for c in pw)
        has_special = any(c in "!@#$%&*" for c in pw)
        if has_upper and has_lower and has_digit and has_special:
            return pw


async def _fetch_user_teams(user_id: UUID) -> list[str]:
    """Fetch team IDs for a user."""
    rows = await fetch_all(
        "SELECT team_id FROM project.hitl_team_members WHERE user_id = $1",
        user_id,
    )
    return [r["team_id"] for r in rows]


async def _build_token_response(
    user_id: str,
    email: str,
    display_name: str,
    role: str,
    auth_type: str,
    culture: str,
    teams: list[str],
) -> TokenResponse:
    """Build a TokenResponse with JWT."""
    token = encode_token(user_id, email, role, teams, culture)
    user = UserResponse(
        id=UUID(user_id),
        email=email,
        display_name=display_name,
        role=role,
        auth_type=auth_type,
        culture=culture,
        teams=teams,
    )
    return TokenResponse(token=token, user=user)


async def login(email: str, password: str) -> TokenResponse:
    """Authenticate with email/password and return JWT."""
    row = await fetch_one(
        """SELECT id, email, password_hash, display_name, role,
                  is_active, COALESCE(auth_type, 'local') as auth_type,
                  COALESCE(culture, 'fr') as culture
           FROM project.hitl_users WHERE email = $1""",
        email,
    )
    if not row:
        raise _error(401, "auth.invalid_credentials")
    if row["auth_type"] == "google":
        raise _error(400, "auth.google_login_required")
    if not row["password_hash"] or not verify_password(password, row["password_hash"]):
        raise _error(401, "auth.invalid_credentials")
    if not row["is_active"]:
        raise _error(403, "auth.account_disabled")
    if row["role"] == "undefined":
        raise _error(403, "auth.account_pending")

    user_id = str(row["id"])
    teams = await _fetch_user_teams(row["id"])

    # Update last_login
    await execute(
        "UPDATE project.hitl_users SET last_login = NOW() WHERE id = $1",
        row["id"],
    )

    return await _build_token_response(
        user_id, row["email"], row["display_name"],
        row["role"], row["auth_type"], row["culture"], teams,
    )


async def register(email: str, culture: str = "fr") -> SuccessResponse:
    """Register a new user with a temporary password."""
    existing = await fetch_one(
        "SELECT id FROM project.hitl_users WHERE email = $1", email,
    )
    if existing:
        raise _error(409, "auth.email_exists")

    temp_pw = _generate_temp_password()
    hashed = hash_password(temp_pw)
    display_name = email.split("@")[0]

    await execute(
        """INSERT INTO project.hitl_users
           (email, password_hash, display_name, role, auth_type, culture)
           VALUES ($1, $2, $3, 'undefined', 'local', $4)""",
        email, hashed, display_name, culture,
    )

    await send_reset_email(email, temp_pw)
    return SuccessResponse(ok=True)


async def google_auth(credential: str) -> TokenResponse:
    """Authenticate via Google ID token."""
    google_cfg = load_json_config("hitl.json").get("google_oauth", {})
    if not google_cfg.get("enabled", False):
        raise _error(400, "auth.google_not_configured")

    client_id = google_cfg.get("client_id", "")
    allowed_domains: list[str] = google_cfg.get("allowed_domains", [])

    # Verify token with Google
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/tokeninfo",
            params={"id_token": credential},
        )
    if resp.status_code != 200:
        raise _error(401, "auth.google_invalid_token")

    info = resp.json()
    if info.get("aud") != client_id:
        raise _error(401, "auth.google_invalid_token")
    if not info.get("email_verified", "false") == "true":
        raise _error(401, "auth.google_invalid_token")

    g_email: str = info["email"]
    domain = g_email.split("@")[1] if "@" in g_email else ""
    if allowed_domains and domain not in allowed_domains:
        raise _error(403, "auth.google_domain_not_allowed")

    # Find or create user
    row = await fetch_one(
        """SELECT id, email, display_name, role, is_active,
                  COALESCE(culture, 'fr') as culture
           FROM project.hitl_users WHERE email = $1""",
        g_email,
    )
    if not row:
        display_name = info.get("name", g_email.split("@")[0])
        await execute(
            """INSERT INTO project.hitl_users
               (email, password_hash, display_name, role, auth_type, culture)
               VALUES ($1, NULL, $2, 'undefined', 'google', 'fr')""",
            g_email, display_name,
        )
        raise _error(403, "auth.account_pending")

    if not row["is_active"]:
        raise _error(403, "auth.account_disabled")
    if row["role"] == "undefined":
        raise _error(403, "auth.account_pending")

    user_id = str(row["id"])
    teams = await _fetch_user_teams(row["id"])

    await execute(
        "UPDATE project.hitl_users SET last_login = NOW() WHERE id = $1",
        row["id"],
    )

    return await _build_token_response(
        user_id, g_email, row["display_name"],
        row["role"], "google", row["culture"], teams,
    )


async def reset_password(
    email: str, old_password: str, new_password: str,
) -> SuccessResponse:
    """Reset password after verifying the old one."""
    if len(new_password) < 6:
        raise _error(400, "auth.weak_password")

    row = await fetch_one(
        "SELECT id, password_hash FROM project.hitl_users WHERE email = $1",
        email,
    )
    if not row or not row["password_hash"]:
        raise _error(401, "auth.password_mismatch")
    if not verify_password(old_password, row["password_hash"]):
        raise _error(401, "auth.password_mismatch")

    hashed = hash_password(new_password)
    await execute(
        "UPDATE project.hitl_users SET password_hash = $1 WHERE id = $2",
        hashed, row["id"],
    )
    return SuccessResponse(ok=True)


async def get_me(user_id: UUID) -> UserResponse:
    """Get current user profile."""
    row = await fetch_one(
        """SELECT id, email, display_name, role,
                  COALESCE(auth_type, 'local') as auth_type,
                  COALESCE(culture, 'fr') as culture
           FROM project.hitl_users WHERE id = $1""",
        user_id,
    )
    if not row:
        raise _error(404, "common.not_found")

    teams = await _fetch_user_teams(user_id)
    return UserResponse(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        role=row["role"],
        auth_type=row["auth_type"],
        culture=row["culture"],
        teams=teams,
    )


def _error(status: int, key: str) -> Exception:
    """Create an HTTPException with an error key."""
    from fastapi import HTTPException
    return HTTPException(status_code=status, detail=key)
