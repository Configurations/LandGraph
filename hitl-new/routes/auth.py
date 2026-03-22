"""Auth routes — login, register, Google OAuth, password reset."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.config import load_json_config
from core.security import TokenData, get_current_user
from schemas.auth import (
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from schemas.common import SuccessResponse
from services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest) -> TokenResponse:
    """Authenticate with email and password."""
    return await auth_service.login(req.email, req.password)


@router.post("/register", response_model=SuccessResponse)
async def register(req: RegisterRequest) -> SuccessResponse:
    """Register a new user (role=undefined until admin approves)."""
    return await auth_service.register(req.email, req.culture)


@router.post("/google", response_model=TokenResponse)
async def google_auth(req: GoogleAuthRequest) -> TokenResponse:
    """Authenticate via Google ID token."""
    return await auth_service.google_auth(req.credential)


@router.get("/google/client-id")
async def google_client_id() -> dict:
    """Return the Google OAuth client ID (or null if disabled)."""
    cfg = load_json_config("hitl.json").get("google_oauth", {})
    if cfg.get("enabled", False):
        return {"client_id": cfg.get("client_id")}
    return {"client_id": None}


@router.get("/me", response_model=UserResponse)
async def me(user: TokenData = Depends(get_current_user)) -> UserResponse:
    """Get current user profile."""
    return await auth_service.get_me(user.user_id)


@router.post("/reset-password", response_model=SuccessResponse)
async def reset_password(req: ResetPasswordRequest) -> SuccessResponse:
    """Reset password with old password verification."""
    return await auth_service.reset_password(
        req.email, req.old_password, req.new_password,
    )
