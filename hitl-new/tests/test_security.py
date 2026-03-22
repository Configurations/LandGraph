"""Tests for core/security.py — JWT and password utilities."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from jose import jwt

from core.security import (
    JWT_ALGORITHM,
    TokenData,
    _get_jwt_secret,
    decode_token,
    encode_token,
    hash_password,
    verify_password,
)


# ── encode / decode roundtrip ──────────────────────────────────

def test_encode_decode_roundtrip():
    uid = str(uuid.uuid4())
    token = encode_token(uid, "a@b.com", "admin", ["t1"], "fr")
    payload = decode_token(token)
    assert payload["sub"] == uid
    assert payload["email"] == "a@b.com"
    assert payload["role"] == "admin"
    assert payload["teams"] == ["t1"]
    assert payload["culture"] == "fr"


def test_decode_expired_token():
    secret = _get_jwt_secret()
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "x@y.com",
        "role": "member",
        "teams": [],
        "culture": "fr",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    token = jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)
    with pytest.raises(Exception):
        decode_token(token)


def test_decode_invalid_token():
    with pytest.raises(Exception):
        decode_token("not-a-real-jwt")


def test_decode_wrong_secret():
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "x@y.com",
        "role": "member",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, "wrong-secret-key-1234567890123456", algorithm=JWT_ALGORITHM)
    with pytest.raises(Exception):
        decode_token(token)


# ── password hashing ───────────────────────────────────────────

def test_hash_verify_roundtrip():
    h = hash_password("MyP@ss123")
    assert verify_password("MyP@ss123", h) is True


def test_verify_wrong_password():
    h = hash_password("correct")
    assert verify_password("wrong", h) is False


def test_password_truncation_72_bytes():
    """Bcrypt silently truncates at 72 bytes. Our code does it explicitly."""
    long_pw = "A" * 100
    h = hash_password(long_pw)
    # First 72 chars match
    assert verify_password("A" * 72, h) is True
    # Full 100 chars also matches (truncated to same 72)
    assert verify_password(long_pw, h) is True


# ── JWT secret hashing for short secrets ───────────────────────

def test_short_secret_is_hashed():
    with patch("core.security.settings") as mock_settings:
        mock_settings.hitl_jwt_secret = "short"
        result = _get_jwt_secret()
        assert len(result) == 64  # sha256 hex


def test_long_secret_used_as_is():
    with patch("core.security.settings") as mock_settings:
        mock_settings.hitl_jwt_secret = "a" * 40
        result = _get_jwt_secret()
        assert result == "a" * 40


# ── TokenData ──────────────────────────────────────────────────

def test_token_data_defaults():
    td = TokenData(user_id=uuid.uuid4(), email="a@b.com", role="member")
    assert td.teams == []
    assert td.culture == "fr"
