"""Auth-related Pydantic v2 schemas."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Email/password login."""

    email: str
    password: str


class RegisterRequest(BaseModel):
    """Register a new user (admin-initiated)."""

    email: str
    culture: str = "fr"


class GoogleAuthRequest(BaseModel):
    """Google OAuth ID token."""

    credential: str


class ResetPasswordRequest(BaseModel):
    """Reset password with old password verification."""

    email: str
    old_password: str
    new_password: str


class TokenResponse(BaseModel):
    """JWT token + user info returned on login."""

    token: str
    user: UserResponse


class UserResponse(BaseModel):
    """Public user representation."""

    id: UUID
    email: str
    display_name: str
    role: str
    auth_type: str
    culture: str
    teams: list[str] = []


# Rebuild TokenResponse now that UserResponse is defined
TokenResponse.model_rebuild()
