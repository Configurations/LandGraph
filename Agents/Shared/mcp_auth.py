"""MCP API Key management — HMAC-signed tokens + PostgreSQL revocation."""
import base64
import hashlib
import hmac as _hmac
import json
import logging
import os
from datetime import datetime, timezone

import psycopg

logger = logging.getLogger("mcp_auth")

MCP_SECRET = os.getenv("MCP_SECRET", "")


# ── Token format ──────────────────────────────────
# lg-<base64url(payload)>.<hmac-sha256(payload, secret)[:16]>
#
# payload = {"teams": [...], "agents": [...], "scopes": [...], "name": "...", "exp": "..."|null}
#
# Scopes control what the token can do. Checked BEFORE any DB hit.
# Available scopes:
#   call_agent  — invoke agents via MCP SSE
KNOWN_SCOPES = {"call_agent"}

def _get_secret() -> str:
    s = os.getenv("MCP_SECRET", "")
    if not s:
        raise ValueError("MCP_SECRET not set in environment")
    return s


def generate_token(name: str, teams: list, agents: list,
                   scopes: list | None = None,
                   expires_at: str | None = None) -> str:
    """Generate a signed API token. Returns the full token (shown once)."""
    secret = _get_secret()
    payload = {
        "teams": teams,
        "agents": agents,
        "scopes": scopes or ["call_agent"],
        "name": name,
    }
    if expires_at:
        payload["exp"] = expires_at

    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode().rstrip("=")
    sig = _hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()[:16]
    return f"lg-{payload_b64}.{sig}"


def verify_token(token: str) -> dict | None:
    """Verify HMAC signature and return claims, or None if invalid."""
    if not token.startswith("lg-"):
        return None
    try:
        secret = _get_secret()
    except ValueError:
        return None

    body = token[3:]  # strip "lg-"
    if "." not in body:
        return None

    payload_b64, sig_received = body.rsplit(".", 1)

    # Restore base64 padding
    padding = 4 - len(payload_b64) % 4
    if padding < 4:
        payload_b64_padded = payload_b64 + "=" * padding
    else:
        payload_b64_padded = payload_b64

    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64_padded)
    except Exception:
        return None

    sig_expected = _hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()[:16]
    if not _hmac.compare_digest(sig_expected, sig_received):
        return None

    try:
        claims = json.loads(payload_bytes)
    except Exception:
        return None

    return claims


def token_hash(token: str) -> str:
    """SHA-256 hash of the full token for DB lookup."""
    return hashlib.sha256(token.encode()).hexdigest()


def token_preview(token: str) -> str:
    """Anonymized preview: lg-xxxx...AbCd"""
    if len(token) > 12:
        return token[:6] + "..." + token[-4:]
    return token[:4] + "..."


# ── DB operations ─────────────────────────────────

def _get_conn():
    uri = os.getenv("DATABASE_URI", "")
    if not uri:
        raise ValueError("DATABASE_URI not set")
    return psycopg.connect(uri, autocommit=True)


def db_register_key(token: str, name: str, teams: list, agents: list,
                    scopes: list | None = None,
                    expires_at: str | None = None):
    """Register a newly generated token in PostgreSQL."""
    h = token_hash(token)
    preview = token_preview(token)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO project.mcp_api_keys
                    (key_hash, name, preview, teams, agents, scopes, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (key_hash) DO NOTHING
            """, (h, name, preview,
                  json.dumps(teams), json.dumps(agents),
                  json.dumps(scopes or ["call_agent"]),
                  expires_at))
    finally:
        conn.close()


def db_check_key(token: str) -> dict | None:
    """Check if token exists in DB, is not revoked, and not expired.
    Returns the DB row as dict, or None."""
    h = token_hash(token)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT key_hash, name, preview, teams, agents, scopes,
                       created_at, expires_at, revoked
                FROM project.mcp_api_keys
                WHERE key_hash = %s
            """, (h,))
            row = cur.fetchone()
            if not row:
                return None
            rec = {
                "key_hash": row[0], "name": row[1], "preview": row[2],
                "teams": row[3], "agents": row[4], "scopes": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
                "expires_at": row[7].isoformat() if row[7] else None,
                "revoked": row[8],
            }
            if rec["revoked"]:
                return None
            if rec["expires_at"]:
                exp = datetime.fromisoformat(rec["expires_at"])
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < datetime.now(timezone.utc):
                    return None
            return rec
    finally:
        conn.close()


def db_list_keys() -> list[dict]:
    """List all API keys (for admin dashboard)."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT key_hash, name, preview, teams, agents, scopes,
                       created_at, expires_at, revoked
                FROM project.mcp_api_keys
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()
            return [{
                "key_hash": r[0], "name": r[1], "preview": r[2],
                "teams": r[3], "agents": r[4], "scopes": r[5],
                "created_at": r[6].isoformat() if r[6] else None,
                "expires_at": r[7].isoformat() if r[7] else None,
                "revoked": r[8],
            } for r in rows]
    finally:
        conn.close()


def db_revoke_key(key_hash: str):
    """Revoke an API key by its hash."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE project.mcp_api_keys SET revoked = true
                WHERE key_hash = %s
            """, (key_hash,))
    finally:
        conn.close()


def db_delete_key(key_hash: str):
    """Permanently delete an API key."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM project.mcp_api_keys WHERE key_hash = %s",
                (key_hash,))
    finally:
        conn.close()


# ── Full validation pipeline ──────────────────────

def validate_token(token: str, team_id: str,
                   required_scope: str = "call_agent") -> dict | None:
    """Full validation: HMAC check → scope check → DB check → team authorization.
    Scopes are checked BEFORE any DB hit (free, self-validating).
    Returns claims dict with allowed agents, or None."""
    # Step 1: verify HMAC signature (no DB hit)
    claims = verify_token(token)
    if claims is None:
        return None

    # Step 2: check required scope (no DB hit)
    token_scopes = claims.get("scopes", [])
    if required_scope and required_scope not in token_scopes:
        logger.warning(f"Token {token_preview(token)} missing scope '{required_scope}'")
        return None

    # Step 3: check team authorization (no DB hit)
    allowed_teams = claims.get("teams", [])
    if "*" not in allowed_teams and team_id not in allowed_teams:
        return None

    # Step 4: check DB (revoked? expired?)
    db_rec = db_check_key(token)
    if db_rec is None:
        return None

    return claims
