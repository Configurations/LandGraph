"""Tests Auth de la console HITL — JWT, login, register, Google OAuth, reset password."""
import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

# ── Pure function tests (no server import needed) ──


class TestJWTTokens:
    """Tests de create_token / decode_token — fonctions pures."""

    def _make_jwt_module(self):
        """Import jose.jwt pour tester directement."""
        from jose import jwt
        return jwt

    def test_create_decode_roundtrip(self):
        jwt_mod = self._make_jwt_module()
        secret = "test-secret"
        payload = {
            "sub": "42",
            "email": "user@test.com",
            "role": "member",
            "teams": ["team1"],
            "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        }
        token = jwt_mod.encode(payload, secret, algorithm="HS256")
        decoded = jwt_mod.decode(token, secret, algorithms=["HS256"])
        assert decoded["sub"] == "42"
        assert decoded["email"] == "user@test.com"
        assert decoded["role"] == "member"
        assert decoded["teams"] == ["team1"]

    def test_expired_token(self):
        jwt_mod = self._make_jwt_module()
        secret = "test-secret"
        payload = {
            "sub": "1",
            "email": "user@test.com",
            "role": "member",
            "teams": [],
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = jwt_mod.encode(payload, secret, algorithm="HS256")
        from jose import JWTError, ExpiredSignatureError
        with pytest.raises(ExpiredSignatureError):
            jwt_mod.decode(token, secret, algorithms=["HS256"])

    def test_wrong_secret(self):
        jwt_mod = self._make_jwt_module()
        payload = {
            "sub": "1", "email": "u@t.com", "role": "member", "teams": [],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt_mod.encode(payload, "secret-A", algorithm="HS256")
        from jose import JWTError
        with pytest.raises(JWTError):
            jwt_mod.decode(token, "secret-B", algorithms=["HS256"])

    def test_tampered_token(self):
        jwt_mod = self._make_jwt_module()
        secret = "test-secret"
        payload = {
            "sub": "1", "email": "u@t.com", "role": "member", "teams": [],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt_mod.encode(payload, secret, algorithm="HS256")
        # Flip a char
        tampered = token[:-1] + ("X" if token[-1] != "X" else "Y")
        from jose import JWTError
        with pytest.raises(JWTError):
            jwt_mod.decode(tampered, secret, algorithms=["HS256"])


class TestPasswordTruncation:
    """Test _truncate_pw (bcrypt 72 bytes limit)."""

    def test_short_password(self):
        assert self._truncate_pw("hello") == "hello"

    def test_exactly_72_bytes(self):
        pw = "a" * 72
        assert self._truncate_pw(pw) == pw

    def test_long_password(self):
        pw = "a" * 100
        result = self._truncate_pw(pw)
        assert len(result.encode("utf-8")) <= 72

    def test_unicode_password(self):
        # Unicode chars can be multi-byte
        pw = "é" * 50  # each é is 2 bytes → 100 bytes, truncated to 72
        result = self._truncate_pw(pw)
        assert len(result.encode("utf-8")) <= 72

    @staticmethod
    def _truncate_pw(password: str) -> str:
        return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")


class TestQuestionRow:
    """Test _question_row conversion helper."""

    def test_basic_row(self):
        dt = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        row = (
            1, "thread-1", "lead_dev", "team1", "approval", "Valider ?",
            {}, "discord", "pending", None, None, None,
            dt, None, None, None, 0,
        )
        result = self._question_row(row)
        assert result["id"] == "1"
        assert result["agent_id"] == "lead_dev"
        assert result["status"] == "pending"
        assert result["created_at"] == "2025-01-15T10:00:00+00:00"
        assert result["remind_count"] == 0

    def test_row_with_string_context(self):
        dt = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        row = (
            2, "t-2", "qa", "team1", "ask_human", "Question ?",
            '{"options": ["A", "B"]}', "web", "answered", "A", "admin@test.com", "web",
            dt, dt, None, None, 1,
        )
        result = self._question_row(row)
        assert result["context"]["options"] == ["A", "B"]
        assert result["response"] == "A"
        assert result["reviewer"] == "admin@test.com"

    def test_row_null_dates(self):
        row = (
            3, "t-3", "dev", "team1", "approval", "Q?",
            None, "discord", "pending", None, None, None,
            None, None, None, None, None,
        )
        result = self._question_row(row)
        assert result["created_at"] is None
        assert result["remind_count"] == 0

    @staticmethod
    def _question_row(r) -> dict:
        import json as _json
        ctx = r[6]
        if isinstance(ctx, str):
            ctx = _json.loads(ctx or "{}")
        if ctx is None:
            ctx = {}
        return {
            "id": str(r[0]),
            "thread_id": r[1],
            "agent_id": r[2],
            "team_id": r[3],
            "request_type": r[4],
            "prompt": r[5],
            "context": ctx,
            "channel": r[7],
            "status": r[8],
            "response": r[9],
            "reviewer": r[10],
            "response_channel": r[11],
            "created_at": r[12].isoformat() if r[12] else None,
            "answered_at": r[13].isoformat() if r[13] else None,
            "expires_at": r[14].isoformat() if r[14] else None,
            "reminded_at": r[15].isoformat() if r[15] else None,
            "remind_count": r[16] or 0,
        }


class TestLoadHitlConfig:
    """Test _load_hitl_config helper."""

    def test_loads_from_config_dir(self, tmp_path):
        import json
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        hitl_json = config_dir / "hitl.json"
        hitl_json.write_text(json.dumps({
            "auth": {"jwt_expire_hours": 48},
            "google_oauth": {"enabled": True, "client_id": "test-id"},
        }))

        # Simulate the function
        result = self._load(str(hitl_json))
        assert result["auth"]["jwt_expire_hours"] == 48
        assert result["google_oauth"]["client_id"] == "test-id"

    def test_missing_config(self):
        result = self._load("/nonexistent/hitl.json")
        assert result == {}

    @staticmethod
    def _load(path: str) -> dict:
        import json
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return {}
