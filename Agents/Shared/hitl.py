"""HITL — Human-In-The-Loop abstraction layer.

Shared queue in PostgreSQL. Any channel (Discord, Email, Web dashboard)
can create requests and submit responses.

Usage (agent side):
    from agents.shared.hitl import create_request, poll_response

    req_id = create_request("approval", agent="architect", prompt="Valider l'ADR ?",
                            thread_id="project-channel-123", team_id="default",
                            channel="discord", context={"summary": "..."}, timeout=1800)
    result = await poll_response(req_id, timeout=1800)
    # result = {"status": "answered", "response": "approve", "reviewer": "john", ...}

Usage (responder side — web dashboard, Discord watcher, etc.):
    from agents.shared.hitl import submit_response
    submit_response(req_id, response="approve", reviewer="john", channel="web")
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import psycopg

logger = logging.getLogger("hitl")


def _get_conn():
    uri = os.getenv("DATABASE_URI", "")
    if not uri:
        raise ValueError("DATABASE_URI not set")
    return psycopg.connect(uri, autocommit=True)


# ── Create ────────────────────────────────────

def create_request(
    request_type: str,
    agent: str,
    prompt: str,
    thread_id: str = "",
    team_id: str = "default",
    channel: str = "discord",
    context: dict | None = None,
    timeout: int = 1800,
) -> str:
    """Insert a HITL request. Returns the UUID as string."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=timeout)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO project.hitl_requests
                    (thread_id, agent_id, team_id, request_type, prompt,
                     context, channel, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                thread_id, agent, team_id, request_type, prompt,
                json.dumps(context or {}), channel, expires_at
            ))
            row = cur.fetchone()
            req_id = str(row[0])
            logger.info(f"HITL request created: {req_id} type={request_type} agent={agent}")
            return req_id
    finally:
        conn.close()


# ── Respond ───────────────────────────────────

def submit_response(
    request_id: str,
    response: str,
    reviewer: str = "",
    channel: str = "web",
) -> bool:
    """Submit a response to a pending HITL request. Returns True if updated."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE project.hitl_requests
                SET status = 'answered',
                    response = %s,
                    reviewer = %s,
                    response_channel = %s,
                    answered_at = NOW()
                WHERE id = %s AND status = 'pending'
            """, (response, reviewer, channel, request_id))
            updated = cur.rowcount > 0
            if updated:
                logger.info(f"HITL response submitted: {request_id} by {reviewer} via {channel}")
            return updated
    finally:
        conn.close()


# ── Poll (used by agents) ─────────────────────

def check_response(request_id: str) -> dict | None:
    """Non-blocking check. Returns the row dict if answered, None if still pending."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, status, response, reviewer, response_channel, answered_at
                FROM project.hitl_requests
                WHERE id = %s
            """, (request_id,))
            row = cur.fetchone()
            if not row:
                return None
            if row[1] != "answered":
                return None
            return {
                "id": str(row[0]),
                "status": row[1],
                "response": row[2] or "",
                "reviewer": row[3] or "",
                "response_channel": row[4] or "",
                "answered_at": row[5].isoformat() if row[5] else None,
            }
    finally:
        conn.close()


def mark_timeout(request_id: str):
    """Mark a request as timed out."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE project.hitl_requests
                SET status = 'timeout', answered_at = NOW()
                WHERE id = %s AND status = 'pending'
            """, (request_id,))
    finally:
        conn.close()


def cancel_request(request_id: str):
    """Cancel a pending request."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE project.hitl_requests
                SET status = 'cancelled', answered_at = NOW()
                WHERE id = %s AND status = 'pending'
            """, (request_id,))
    finally:
        conn.close()


# ── List (used by dashboard) ──────────────────

def list_requests(
    status: str | None = None,
    team_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List HITL requests, most recent first."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            clauses = []
            params = []
            if status:
                clauses.append("status = %s")
                params.append(status)
            if team_id:
                clauses.append("team_id = %s")
                params.append(team_id)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            cur.execute(f"""
                SELECT id, thread_id, agent_id, team_id, request_type, prompt,
                       context, channel, status, response, reviewer,
                       response_channel, created_at, answered_at, expires_at
                FROM project.hitl_requests
                {where}
                ORDER BY created_at DESC
                LIMIT %s
            """, (*params, limit))
            rows = cur.fetchall()
            return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_request(request_id: str) -> dict | None:
    """Get a single HITL request by ID."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, thread_id, agent_id, team_id, request_type, prompt,
                       context, channel, status, response, reviewer,
                       response_channel, created_at, answered_at, expires_at
                FROM project.hitl_requests
                WHERE id = %s
            """, (request_id,))
            row = cur.fetchone()
            if not row:
                return None
            return _row_to_dict(row)
    finally:
        conn.close()


def _row_to_dict(r) -> dict:
    return {
        "id": str(r[0]),
        "thread_id": r[1],
        "agent_id": r[2],
        "team_id": r[3],
        "request_type": r[4],
        "prompt": r[5],
        "context": r[6] if isinstance(r[6], dict) else json.loads(r[6] or "{}"),
        "channel": r[7],
        "status": r[8],
        "response": r[9],
        "reviewer": r[10],
        "response_channel": r[11],
        "created_at": r[12].isoformat() if r[12] else None,
        "answered_at": r[13].isoformat() if r[13] else None,
        "expires_at": r[14].isoformat() if r[14] else None,
    }


# ── Stats ─────────────────────────────────────

def get_stats() -> dict:
    """Quick stats for dashboard header."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT status, COUNT(*)
                FROM project.hitl_requests
                GROUP BY status
            """)
            counts = {r[0]: r[1] for r in cur.fetchall()}
            return {
                "pending": counts.get("pending", 0),
                "answered": counts.get("answered", 0),
                "timeout": counts.get("timeout", 0),
                "cancelled": counts.get("cancelled", 0),
                "total": sum(counts.values()),
            }
    finally:
        conn.close()
