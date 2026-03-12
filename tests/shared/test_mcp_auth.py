"""Tests pour mcp_auth.py — generation/verification HMAC tokens."""
import os
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def _set_mcp_secret(monkeypatch):
    monkeypatch.setenv("MCP_SECRET", "test-secret-key-for-unit-tests")


# ── generate_token ───────────────────────────────

class TestGenerateToken:
    def test_format_prefix(self):
        from agents.shared.mcp_auth import generate_token
        token = generate_token("test", ["team1"], ["lead_dev"])
        assert token.startswith("lg-")

    def test_format_has_dot(self):
        from agents.shared.mcp_auth import generate_token
        token = generate_token("test", ["team1"], ["lead_dev"])
        body = token[3:]  # strip lg-
        assert "." in body

    def test_default_scopes(self):
        from agents.shared.mcp_auth import generate_token, verify_token
        token = generate_token("test", ["team1"], ["lead_dev"])
        claims = verify_token(token)
        assert "call_agent" in claims["scopes"]

    def test_custom_scopes(self):
        from agents.shared.mcp_auth import generate_token, verify_token
        token = generate_token("test", ["team1"], ["lead_dev"], scopes=["custom"])
        claims = verify_token(token)
        assert claims["scopes"] == ["custom"]

    def test_with_expiry(self):
        from agents.shared.mcp_auth import generate_token, verify_token
        token = generate_token("test", ["team1"], ["lead_dev"], expires_at="2099-01-01T00:00:00Z")
        claims = verify_token(token)
        assert claims["exp"] == "2099-01-01T00:00:00Z"

    def test_without_expiry(self):
        from agents.shared.mcp_auth import generate_token, verify_token
        token = generate_token("test", ["team1"], ["lead_dev"])
        claims = verify_token(token)
        assert "exp" not in claims


# ── verify_token ─────────────────────────────────

class TestVerifyToken:
    def test_roundtrip(self):
        from agents.shared.mcp_auth import generate_token, verify_token
        token = generate_token("roundtrip", ["team1"], ["arch"])
        claims = verify_token(token)
        assert claims is not None
        assert claims["name"] == "roundtrip"
        assert claims["teams"] == ["team1"]
        assert claims["agents"] == ["arch"]

    def test_tampered_payload(self):
        from agents.shared.mcp_auth import generate_token, verify_token
        token = generate_token("test", ["team1"], ["a"])
        # Modify a character in payload
        parts = token.split(".")
        tampered = parts[0] + "X" + "." + parts[1]
        assert verify_token(tampered) is None

    def test_tampered_signature(self):
        from agents.shared.mcp_auth import generate_token, verify_token
        token = generate_token("test", ["team1"], ["a"])
        # Modify the signature
        assert verify_token(token[:-1] + "X") is None

    def test_no_prefix(self):
        from agents.shared.mcp_auth import verify_token
        assert verify_token("not-a-token") is None

    def test_no_dot(self):
        from agents.shared.mcp_auth import verify_token
        assert verify_token("lg-nodothere") is None

    def test_no_secret(self, monkeypatch):
        monkeypatch.setenv("MCP_SECRET", "")
        from agents.shared.mcp_auth import verify_token
        assert verify_token("lg-something.sig") is None


# ── token_hash ───────────────────────────────────

class TestTokenHash:
    def test_deterministic(self):
        from agents.shared.mcp_auth import token_hash
        h1 = token_hash("lg-abc.def")
        h2 = token_hash("lg-abc.def")
        assert h1 == h2

    def test_different_tokens_different_hashes(self):
        from agents.shared.mcp_auth import token_hash
        assert token_hash("lg-a.1") != token_hash("lg-b.2")

    def test_sha256_length(self):
        from agents.shared.mcp_auth import token_hash
        h = token_hash("test")
        assert len(h) == 64  # hex SHA-256


# ── token_preview ────────────────────────────────

class TestTokenPreview:
    def test_long_token(self):
        from agents.shared.mcp_auth import token_preview
        preview = token_preview("lg-abcdefghijklmnop.sig12345")
        assert preview.startswith("lg-abc")
        assert "..." in preview

    def test_short_token(self):
        from agents.shared.mcp_auth import token_preview
        preview = token_preview("lg-short")
        assert "..." in preview


# ── validate_token (sans DB) ─────────────────────

class TestValidateToken:
    def test_wrong_team_rejected(self):
        from agents.shared.mcp_auth import generate_token, validate_token
        token = generate_token("test", ["team1"], ["a"])
        with patch("Agents.Shared.mcp_auth.db_check_key", return_value={"key_hash": "h"}):
            result = validate_token(token, "team2")
            assert result is None

    def test_wildcard_team_accepted(self):
        from agents.shared.mcp_auth import generate_token, validate_token
        token = generate_token("test", ["*"], ["a"])
        with patch("Agents.Shared.mcp_auth.db_check_key", return_value={"key_hash": "h"}):
            result = validate_token(token, "any_team")
            assert result is not None

    def test_missing_scope_rejected(self):
        from agents.shared.mcp_auth import generate_token, validate_token
        token = generate_token("test", ["team1"], ["a"], scopes=["other_scope"])
        result = validate_token(token, "team1", required_scope="call_agent")
        assert result is None

    def test_hmac_fail_rejected(self):
        from agents.shared.mcp_auth import validate_token
        result = validate_token("lg-invalid.token", "team1")
        assert result is None

    def test_db_revoked_rejected(self):
        from agents.shared.mcp_auth import generate_token, validate_token
        token = generate_token("test", ["team1"], ["a"])
        with patch("Agents.Shared.mcp_auth.db_check_key", return_value=None):
            result = validate_token(token, "team1")
            assert result is None

    def test_full_success(self):
        from agents.shared.mcp_auth import generate_token, validate_token
        token = generate_token("test", ["team1"], ["a"])
        with patch("Agents.Shared.mcp_auth.db_check_key", return_value={"key_hash": "h"}):
            result = validate_token(token, "team1")
            assert result is not None
            assert result["name"] == "test"
